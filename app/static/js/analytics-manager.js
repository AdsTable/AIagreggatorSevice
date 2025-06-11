/**
 * Robust Analytics Manager with Error Handling and Privacy Support
 * Handles blocked requests gracefully and provides fallback mechanisms
 * 
 * @author AdsTable Team
 * @version 1.0.0
 * @date 2025-06-11
 */

class RobustAnalyticsManager {
    constructor(config = {}) {
        this.config = {
            enableClientSideTracking: true,
            enableServerSideTracking: true,
            respectDoNotTrack: true,
            fallbackToLocalStorage: true,
            debugMode: config.debugMode || false,
            apiEndpoint: '/api/analytics/track',
            ...config
        };
        
        this.isBlocked = false;
        this.fallbackQueue = [];
        this.segmentInstance = null;
        this.initialized = false;
        
        this.initializeAnalytics();
    }

    /**
     * Initialize analytics with comprehensive error handling
     */
    async initializeAnalytics() {
        try {
            // Check if user has Do Not Track enabled
            if (this.config.respectDoNotTrack && this.isDoNotTrackEnabled()) {
                this.log('Do Not Track detected - analytics disabled');
                return;
            }

            // Check if analytics is likely to be blocked
            if (await this.detectAnalyticsBlocking()) {
                this.log('Analytics blocking detected - enabling fallback mode');
                this.isBlocked = true;
                this.initializeFallbackAnalytics();
                return;
            }

            // Initialize Segment.io with error handling
            if (this.config.enableClientSideTracking) {
                await this.initializeSegment();
            }

            this.initialized = true;
            this.log('Analytics initialized successfully');

        } catch (error) {
            this.warn('Failed to initialize analytics:', error);
            this.handleAnalyticsError(error);
        }
    }

    /**
     * Detect if analytics requests are being blocked
     */
    async detectAnalyticsBlocking() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 1000);

            // Test request to Segment API with short timeout
            const response = await fetch('https://api.segment.io/v1/p', {
                method: 'HEAD',
                signal: controller.signal,
                mode: 'no-cors'
            });

            clearTimeout(timeoutId);
            return false; // Not blocked
        } catch (error) {
            // Check specific error types that indicate blocking
            if (error.name === 'AbortError' || 
                error.message.includes('blocked') ||
                error.message.includes('ERR_BLOCKED_BY_CLIENT')) {
                return true; // Likely blocked
            }
            return false;
        }
    }

    /**
     * Check if Do Not Track is enabled
     */
    isDoNotTrackEnabled() {
        return navigator.doNotTrack === '1' || 
               window.doNotTrack === '1' || 
               navigator.msDoNotTrack === '1';
    }

    /**
     * Initialize Segment.io with comprehensive error handling
     */
    async initializeSegment() {
        try {
            // Check if analytics global is available
            if (typeof analytics !== 'undefined' && analytics) {
                this.segmentInstance = analytics;
                
                // Override Segment's error handling
                this.segmentInstance.on('error', (error) => {
                    this.warn('Segment error:', error);
                    this.handleAnalyticsError(error);
                });

                // Test Segment functionality
                await this.testSegmentConnection();
                this.log('Segment initialized successfully');
            } else {
                throw new Error('Segment analytics not available');
            }
        } catch (error) {
            this.warn('Segment initialization failed:', error);
            this.isBlocked = true;
            this.initializeFallbackAnalytics();
        }
    }

    /**
     * Test Segment connection with a minimal event
     */
    async testSegmentConnection() {
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error('Segment connection test timeout'));
            }, 2000);

            try {
                // Send a test event that won't affect real analytics
                this.segmentInstance.track('analytics_health_check', 
                    { test: true, timestamp: new Date().toISOString() }, 
                    {
                        context: { 
                            library: { name: 'robust-analytics', version: '1.0.0' } 
                        }
                    }
                );
                
                clearTimeout(timeout);
                resolve();
            } catch (error) {
                clearTimeout(timeout);
                reject(error);
            }
        });
    }

    /**
     * Initialize fallback analytics for when main analytics is blocked
     */
    initializeFallbackAnalytics() {
        this.log('Initializing fallback analytics');
        
        if (this.config.enableServerSideTracking) {
            this.setupServerSideTracking();
        }

        if (this.config.fallbackToLocalStorage) {
            this.setupLocalStorageFallback();
        }
    }

    /**
     * Setup server-side tracking as fallback
     */
    setupServerSideTracking() {
        this.log('Server-side tracking enabled');
        // Server-side tracking is handled in track() method
    }

    /**
     * Setup local storage fallback for offline analytics
     */
    setupLocalStorageFallback() {
        try {
            const storedEvents = localStorage.getItem('analytics_fallback');
            if (storedEvents) {
                this.fallbackQueue = JSON.parse(storedEvents);
                this.log(`Loaded ${this.fallbackQueue.length} events from local storage`);
            }
        } catch (error) {
            this.warn('Local storage fallback setup failed:', error);
        }
    }

    /**
     * Track event with comprehensive error handling
     * @param {string} eventName - Name of the event to track
     * @param {Object} properties - Event properties
     */
    track(eventName, properties = {}) {
        try {
            // Check if tracking is enabled
            if (this.isDoNotTrackEnabled() && this.config.respectDoNotTrack) {
                this.log(`Event not tracked due to Do Not Track: ${eventName}`);
                return;
            }

            const event = {
                event: eventName,
                properties: this.sanitizeProperties(properties),
                timestamp: new Date().toISOString(),
                anonymousId: this.getAnonymousId(),
                sessionId: this.getSessionId()
            };

            // Try primary analytics (Segment)
            if (this.segmentInstance && !this.isBlocked) {
                this.trackWithSegment(event);
            } else {
                // Use fallback tracking
                this.trackWithFallback(event);
            }

            this.log(`Event tracked: ${eventName}`, event);

        } catch (error) {
            this.warn('Track error:', error);
            this.handleAnalyticsError(error);
        }
    }

    /**
     * Track with Segment.io with error handling
     */
    trackWithSegment(event) {
        try {
            this.segmentInstance.track(event.event, event.properties, {
                anonymousId: event.anonymousId,
                timestamp: event.timestamp
            });
        } catch (error) {
            this.warn('Segment tracking failed:', error);
            this.isBlocked = true;
            this.trackWithFallback(event);
        }
    }

    /**
     * Track with fallback methods
     */
    trackWithFallback(event) {
        // Add to fallback queue
        this.fallbackQueue.push(event);

        // Try server-side tracking
        if (this.config.enableServerSideTracking) {
            this.sendToServer(event);
        }

        // Store in local storage
        if (this.config.fallbackToLocalStorage) {
            this.storeLocally();
        }
    }

    /**
     * Send event to server-side analytics endpoint
     */
    async sendToServer(event) {
        try {
            const response = await fetch(this.config.apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(event)
            });

            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}`);
            }

            this.log('Event sent to server successfully');
        } catch (error) {
            this.warn('Server-side tracking failed:', error);
        }
    }

    /**
     * Store events in local storage
     */
    storeLocally() {
        try {
            // Keep only last 100 events to prevent storage bloat
            if (this.fallbackQueue.length > 100) {
                this.fallbackQueue = this.fallbackQueue.slice(-100);
            }

            localStorage.setItem('analytics_fallback', JSON.stringify(this.fallbackQueue));
        } catch (error) {
            this.warn('Local storage failed:', error);
        }
    }

    /**
     * Sanitize properties to remove sensitive data
     */
    sanitizeProperties(properties) {
        const sanitized = { ...properties };
        const sensitiveKeys = ['password', 'token', 'key', 'secret', 'api_key'];
        
        Object.keys(sanitized).forEach(key => {
            if (sensitiveKeys.some(sensitive => key.toLowerCase().includes(sensitive))) {
                delete sanitized[key];
            }
        });

        return sanitized;
    }

    /**
     * Get or generate anonymous ID
     */
    getAnonymousId() {
        try {
            let anonymousId = localStorage.getItem('analytics_anonymous_id');
            if (!anonymousId) {
                anonymousId = 'anon_' + Math.random().toString(36).substr(2, 12) + '_' + Date.now();
                localStorage.setItem('analytics_anonymous_id', anonymousId);
            }
            return anonymousId;
        } catch (error) {
            // Fallback to session-based ID
            return 'session_' + Math.random().toString(36).substr(2, 12);
        }
    }

    /**
     * Get or generate session ID
     */
    getSessionId() {
        try {
            let sessionId = sessionStorage.getItem('analytics_session_id');
            if (!sessionId) {
                sessionId = 'sess_' + Math.random().toString(36).substr(2, 12) + '_' + Date.now();
                sessionStorage.setItem('analytics_session_id', sessionId);
            }
            return sessionId;
        } catch (error) {
            return 'temp_' + Math.random().toString(36).substr(2, 12);
        }
    }

    /**
     * Handle analytics errors gracefully
     */
    handleAnalyticsError(error) {
        // Mark as blocked if it's a blocking error
        if (error.message && error.message.includes('blocked')) {
            this.isBlocked = true;
            this.initializeFallbackAnalytics();
        }

        // Report error to monitoring
        this.reportAnalyticsError(error);
    }

    /**
     * Report analytics errors to monitoring
     */
    reportAnalyticsError(error) {
        try {
            fetch('/api/monitoring/analytics-error', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    error: error.message,
                    stack: error.stack,
                    userAgent: navigator.userAgent,
                    url: window.location.href,
                    timestamp: new Date().toISOString()
                })
            }).catch(() => {
                // Silently fail if monitoring is also blocked
            });
        } catch (error) {
            // Silently handle monitoring errors
        }
    }

    /**
     * Get analytics status for debugging
     */
    getStatus() {
        return {
            initialized: this.initialized,
            isBlocked: this.isBlocked,
            doNotTrack: this.isDoNotTrackEnabled(),
            segmentAvailable: !!this.segmentInstance,
            fallbackQueueSize: this.fallbackQueue.length,
            config: this.config
        };
    }

    /**
     * Manually retry analytics initialization
     */
    async retry() {
        this.isBlocked = false;
        this.initialized = false;
        await this.initializeAnalytics();
    }

    /**
     * Logging helper
     */
    log(message, data = null) {
        if (this.config.debugMode) {
            console.log(`[Analytics] ${message}`, data || '');
        }
    }

    /**
     * Warning helper
     */
    warn(message, error = null) {
        if (this.config.debugMode) {
            console.warn(`[Analytics] ${message}`, error || '');
        }
    }
}

// Global analytics instance
window.robustAnalytics = new RobustAnalyticsManager({
    debugMode: true // Set to false in production
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = RobustAnalyticsManager;
}