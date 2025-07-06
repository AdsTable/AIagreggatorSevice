# app\static\js\analytics-manager.js v.1
/**
 * Enhanced Analytics Manager with Error Handling and Privacy Support
 * Handles blocked requests gracefully and provides fallback mechanisms
 */

interface AnalyticsConfig {
  enableClientSideTracking: boolean;
  enableServerSideTracking: boolean;
  respectDoNotTrack: boolean;
  fallbackToLocalStorage: boolean;
  debugMode: boolean;
}

interface AnalyticsEvent {
  event: string;
  properties?: Record<string, any>;
  userId?: string;
  anonymousId?: string;
  timestamp: string;
}

class RobustAnalyticsManager {
  private config: AnalyticsConfig;
  private isBlocked: boolean = false;
  private fallbackQueue: AnalyticsEvent[] = [];
  private segmentInstance: any = null;
  
  constructor(config: AnalyticsConfig) {
    this.config = config;
    this.initializeAnalytics();
  }

  /**
   * Initialize analytics with error handling and fallback mechanisms
   */
  private async initializeAnalytics(): Promise<void> {
    try {
      // Check if user has Do Not Track enabled
      if (this.config.respectDoNotTrack && this.isDoNotTrackEnabled()) {
        console.log('[Analytics] Do Not Track detected - analytics disabled');
        return;
      }

      // Check if analytics is likely to be blocked
      if (await this.detectAnalyticsBlocking()) {
        console.log('[Analytics] Analytics blocking detected - enabling fallback mode');
        this.isBlocked = true;
        this.initializeFallbackAnalytics();
        return;
      }

      // Initialize Segment.io with error handling
      if (this.config.enableClientSideTracking) {
        await this.initializeSegment();
      }

    } catch (error) {
      console.warn('[Analytics] Failed to initialize analytics:', error);
      this.handleAnalyticsError(error);
    }
  }

  /**
   * Detect if analytics requests are being blocked
   */
  private async detectAnalyticsBlocking(): Promise<boolean> {
    try {
      // Test request to Segment API with short timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1000);

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
  private isDoNotTrackEnabled(): boolean {
    return navigator.doNotTrack === '1' || 
           (window as any).doNotTrack === '1' || 
           navigator.msDoNotTrack === '1';
  }

  /**
   * Initialize Segment.io with comprehensive error handling
   */
  private async initializeSegment(): Promise<void> {
    try {
      // Wrap Segment initialization in try-catch
      if (typeof analytics !== 'undefined') {
        this.segmentInstance = analytics;
        
        // Override Segment's error handling
        this.segmentInstance.on('error', (error: any) => {
          console.warn('[Analytics] Segment error:', error);
          this.handleAnalyticsError(error);
        });

        // Test Segment functionality
        await this.testSegmentConnection();
      }
    } catch (error) {
      console.warn('[Analytics] Segment initialization failed:', error);
      this.isBlocked = true;
      this.initializeFallbackAnalytics();
    }
  }

  /**
   * Test Segment connection with a minimal event
   */
  private async testSegmentConnection(): Promise<void> {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Segment connection test timeout'));
      }, 2000);

      try {
        this.segmentInstance.track('analytics_test', { test: true }, {
          context: { library: { name: 'test', version: '1.0.0' } }
        });
        
        // If no error thrown, assume success
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
  private initializeFallbackAnalytics(): void {
    if (this.config.enableServerSideTracking) {
      console.log('[Analytics] Initializing server-side fallback');
      this.setupServerSideTracking();
    }

    if (this.config.fallbackToLocalStorage) {
      console.log('[Analytics] Initializing local storage fallback');
      this.setupLocalStorageFallback();
    }
  }

  /**
   * Setup server-side tracking as fallback
   */
  private setupServerSideTracking(): void {
    // Send analytics events to your own server endpoint
    // This bypasses client-side blocking
  }

  /**
   * Setup local storage fallback for offline analytics
   */
  private setupLocalStorageFallback(): void {
    try {
      // Store events locally and sync when possible
      const storedEvents = localStorage.getItem('analytics_fallback');
      if (storedEvents) {
        this.fallbackQueue = JSON.parse(storedEvents);
      }
    } catch (error) {
      console.warn('[Analytics] Local storage fallback setup failed:', error);
    }
  }

  /**
   * Track event with comprehensive error handling
   */
  public track(eventName: string, properties: Record<string, any> = {}): void {
    try {
      // Check if tracking is enabled
      if (this.isDoNotTrackEnabled() && this.config.respectDoNotTrack) {
        if (this.config.debugMode) {
          console.log('[Analytics] Event not tracked due to Do Not Track:', eventName);
        }
        return;
      }

      const event: AnalyticsEvent = {
        event: eventName,
        properties: this.sanitizeProperties(properties),
        timestamp: new Date().toISOString(),
        anonymousId: this.getAnonymousId()
      };

      // Try primary analytics (Segment)
      if (this.segmentInstance && !this.isBlocked) {
        this.trackWithSegment(event);
      } else {
        // Use fallback tracking
        this.trackWithFallback(event);
      }

      if (this.config.debugMode) {
        console.log('[Analytics] Event tracked:', event);
      }

    } catch (error) {
      console.warn('[Analytics] Track error:', error);
      this.handleAnalyticsError(error);
    }
  }

  /**
   * Track with Segment.io with error handling
   */
  private trackWithSegment(event: AnalyticsEvent): void {
    try {
      this.segmentInstance.track(event.event, event.properties, {
        anonymousId: event.anonymousId,
        timestamp: event.timestamp
      });
    } catch (error) {
      console.warn('[Analytics] Segment tracking failed:', error);
      this.isBlocked = true;
      this.trackWithFallback(event);
    }
  }

  /**
   * Track with fallback methods
   */
  private trackWithFallback(event: AnalyticsEvent): void {
    // Add to fallback queue
    this.fallbackQueue.push(event);

    // Try server-side tracking
    if (this.config.enableServerSideTracking) {
      this.sendToServer(event);
    }

    // Store in local storage
    if (this.config.fallbackToLocalStorage) {
      this.storeLocally(event);
    }
  }

  /**
   * Send event to server-side analytics endpoint
   */
  private async sendToServer(event: AnalyticsEvent): Promise<void> {
    try {
      await fetch('/api/analytics/track', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(event)
      });
    } catch (error) {
      console.warn('[Analytics] Server-side tracking failed:', error);
    }
  }

  /**
   * Store event in local storage
   */
  private storeLocally(event: AnalyticsEvent): void {
    try {
      // Keep only last 100 events to prevent storage bloat
      if (this.fallbackQueue.length > 100) {
        this.fallbackQueue = this.fallbackQueue.slice(-100);
      }

      localStorage.setItem('analytics_fallback', JSON.stringify(this.fallbackQueue));
    } catch (error) {
      console.warn('[Analytics] Local storage failed:', error);
    }
  }

  /**
   * Sanitize properties to remove sensitive data
   */
  private sanitizeProperties(properties: Record<string, any>): Record<string, any> {
    const sanitized = { ...properties };
    const sensitiveKeys = ['password', 'token', 'key', 'secret', 'email', 'phone'];
    
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
  private getAnonymousId(): string {
    try {
      let anonymousId = localStorage.getItem('analytics_anonymous_id');
      if (!anonymousId) {
        anonymousId = 'anon_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('analytics_anonymous_id', anonymousId);
      }
      return anonymousId;
    } catch (error) {
      // Fallback to session-based ID
      return 'session_' + Math.random().toString(36).substr(2, 9);
    }
  }

  /**
   * Handle analytics errors gracefully
   */
  private handleAnalyticsError(error: any): void {
    // Log error for debugging
    if (this.config.debugMode) {
      console.error('[Analytics] Error details:', error);
    }

    // Mark as blocked if it's a blocking error
    if (error.message && error.message.includes('blocked')) {
      this.isBlocked = true;
      this.initializeFallbackAnalytics();
    }

    // Optional: Send error to monitoring service
    this.reportAnalyticsError(error);
  }

  /**
   * Report analytics errors to monitoring
   */
  private reportAnalyticsError(error: any): void {
    try {
      // Send to your error monitoring service
      fetch('/api/monitoring/analytics-error', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          error: error.message,
          stack: error.stack,
          userAgent: navigator.userAgent,
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
  public getStatus(): Record<string, any> {
    return {
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
  public async retry(): Promise<void> {
    this.isBlocked = false;
    await this.initializeAnalytics();
  }
}

// Server-side analytics endpoint (Express.js example)
export const createAnalyticsEndpoint = (app: any) => {
  app.post('/api/analytics/track', async (req: any, res: any) => {
    try {
      const event = req.body;
      
      // Validate event structure
      if (!event.event || !event.timestamp) {
        return res.status(400).json({ error: 'Invalid event structure' });
      }

      // Process server-side analytics
      // Send to your analytics backend, database, or external service
      await processServerSideAnalytics(event);

      res.status(200).json({ success: true });
    } catch (error) {
      console.error('Server-side analytics error:', error);
      res.status(500).json({ error: 'Analytics processing failed' });
    }
  });
};

async function processServerSideAnalytics(event: AnalyticsEvent): Promise<void> {
  // Implement your server-side analytics logic here
  // Examples:
  // - Send to Google Analytics via Measurement Protocol
  // - Store in database for analysis
  // - Forward to other analytics services
  // - Generate business intelligence reports
}

// Usage example
const analyticsManager = new RobustAnalyticsManager({
  enableClientSideTracking: true,
  enableServerSideTracking: true,
  respectDoNotTrack: true,
  fallbackToLocalStorage: true,
  debugMode: process.env.NODE_ENV === 'development'
});

// Track events with automatic error handling
analyticsManager.track('page_view', {
  page: '/dashboard',
  user_type: 'authenticated'
});

analyticsManager.track('ai_request', {
  provider: 'openai',
  model: 'gpt-4',
  response_time: 1200
});

export default analyticsManager;