/**
 * Dashboard functionality and real-time updates
 * @author AdsTable Team
 * @version 1.0.0
 */

class Dashboard {
    constructor() {
        this.updateInterval = 30000; // 30 seconds
        this.chart = null;
        this.intervalId = null;
        
        this.init();
    }
    
    async init() {
        await this.loadSystemStatus();
        await this.loadProviderStatus();
        await this.loadAnalytics();
        this.initializeChart();
        this.startAutoRefresh();
        this.bindEvents();
    }
    
    async loadSystemStatus() {
        try {
            const response = await fetch('/health');
            const data = await response.json();
            
            this.updateSystemStatus(data);
            this.updateSystemMetrics(data);
        } catch (error) {
            console.error('Failed to load system status:', error);
            this.showError('Failed to load system status');
        }
    }
    
    async loadProviderStatus() {
        try {
            const response = await fetch('/providers');
            const data = await response.json();
            
            this.updateProviderStatus(data);
        } catch (error) {
            console.error('Failed to load provider status:', error);
        }
    }
    
    async loadAnalytics() {
        try {
            const response = await fetch('/api/analytics/dashboard');
            const data = await response.json();
            
            this.updateAnalytics(data);
        } catch (error) {
            console.error('Failed to load analytics:', error);
        }
    }
    
    updateSystemStatus(data) {
        const statusElement = document.getElementById('system-status');
        const healthElement = document.getElementById('health-status');
        
        if (statusElement && healthElement) {
            const isHealthy = data.status === 'healthy';
            const statusClass = isHealthy ? 'status-healthy' : 'status-error';
            const statusText = isHealthy ? 'System Healthy' : 'System Issues';
            
            // Update header status
            const headerDot = statusElement.querySelector('.status-dot');
            headerDot.className = `status-dot ${statusClass}`;
            
            // Update dashboard status
            const dashboardDot = healthElement.querySelector('.status-dot');
            const dashboardText = healthElement.querySelector('.status-text');
            dashboardDot.className = `status-dot ${statusClass}`;
            dashboardText.textContent = statusText;
        }
    }
    
    /**
     * Update system metrics display with real-time data
     * @param {Object} data - System health data from API
     */
    updateSystemMetrics(data) {
        try {
            // Calculate uptime from startup timestamp
            const uptimeElement = document.getElementById('system-uptime');
            if (uptimeElement && data.timestamp && data.startup_state?.startup_time) {
                const startTime = new Date(data.startup_state.startup_time);
                const currentTime = new Date(data.timestamp);
                const uptimeMs = currentTime - startTime;
                const uptimeFormatted = this.formatUptime(uptimeMs);
                uptimeElement.textContent = uptimeFormatted;
            }

            // Update requests per minute
            const requestsElement = document.getElementById('requests-per-minute');
            if (requestsElement) {
                const requestsPerMin = this.calculateRequestsPerMinute(data);
                requestsElement.textContent = requestsPerMin.toString();
            }

            // Update active providers count
            const providersElement = document.getElementById('active-providers');
            if (providersElement && data.components?.providers) {
                const activeCount = data.components.providers.count || 0;
                providersElement.textContent = activeCount.toString();
            }

            // Update error rate
            const errorRateElement = document.getElementById('error-rate');
            if (errorRateElement) {
                const errorRate = this.calculateErrorRate(data);
                errorRateElement.textContent = `${errorRate}%`;
                
                // Add color coding based on error rate
                errorRateElement.className = 'metric-value';
                if (errorRate > 10) {
                    errorRateElement.classList.add('metric-error');
                } else if (errorRate > 5) {
                    errorRateElement.classList.add('metric-warning');
                } else {
                    errorRateElement.classList.add('metric-success');
                }
            }

            // Track metrics update for analytics
            if (window.AIAggregator) {
                window.AIAggregator.trackFeature('dashboard_metrics_updated', {
                    uptime_hours: Math.floor((Date.now() - new Date(data.startup_state?.startup_time || Date.now())) / (1000 * 60 * 60)),
                    active_providers: data.components?.providers?.count || 0,
                    error_rate: this.calculateErrorRate(data)
                });
            }

        } catch (error) {
            console.error('Error updating system metrics:', error);
            this.showError('Failed to update system metrics');
        }
    }

    /**
     * Update provider status display
     * @param {Object} data - Provider data from API
     */
    updateProviderStatus(data) {
        const providerElement = document.getElementById('provider-status');
        if (!providerElement) return;

        try {
            if (data && data.providers && Array.isArray(data.providers)) {
                const providerHtml = data.providers.map(provider => `
                    <div class="provider-item">
                        <div class="provider-info">
                            <span class="provider-name">${this.escapeHtml(provider.name)}</span>
                            <span class="provider-type">${this.escapeHtml(provider.type || 'Unknown')}</span>
                        </div>
                        <div class="provider-status-indicator">
                            <span class="status-dot ${this.getProviderStatusClass(provider.status)}"></span>
                            <span class="status-text">${this.escapeHtml(provider.status || 'Unknown')}</span>
                        </div>
                    </div>
                `).join('');

                providerElement.innerHTML = providerHtml || '<div class="no-data">No providers available</div>';
            } else {
                providerElement.innerHTML = '<div class="no-data">Loading providers...</div>';
            }
        } catch (error) {
            console.error('Error updating provider status:', error);
            providerElement.innerHTML = '<div class="error-message">Failed to load providers</div>';
        }
    }

    /**
     * Update analytics summary display
     * @param {Object} data - Analytics data from API
     */
    updateAnalytics(data) {
        const analyticsElement = document.getElementById('analytics-summary');
        if (!analyticsElement) return;

        try {
            if (data && data.summary) {
                const summary = data.summary;
                const analyticsHtml = `
                    <div class="analytics-grid">
                        <div class="analytics-item">
                            <span class="analytics-value">${this.formatNumber(summary.total_events || 0)}</span>
                            <span class="analytics-label">Total Events</span>
                        </div>
                        <div class="analytics-item">
                            <span class="analytics-value">${this.formatNumber(summary.unique_sessions || 0)}</span>
                            <span class="analytics-label">Active Sessions</span>
                        </div>
                        <div class="analytics-item">
                            <span class="analytics-value">${this.formatNumber(summary.unique_users || 0)}</span>
                            <span class="analytics-label">Unique Users</span>
                        </div>
                        <div class="analytics-item">
                            <span class="analytics-value ${summary.error_count > 0 ? 'error' : 'success'}">
                                ${this.formatNumber(summary.error_count || 0)}
                            </span>
                            <span class="analytics-label">Errors</span>
                        </div>
                    </div>
                `;
                analyticsElement.innerHTML = analyticsHtml;
            } else {
                analyticsElement.innerHTML = '<div class="no-data">No analytics data available</div>';
            }
        } catch (error) {
            console.error('Error updating analytics:', error);
            analyticsElement.innerHTML = '<div class="error-message">Failed to load analytics</div>';
        }
    }

    /**
     * Initialize Chart.js chart for performance metrics
     */
    initializeChart() {
        const chartCanvas = document.getElementById('main-chart');
        if (!chartCanvas) return;

        try {
            const ctx = chartCanvas.getContext('2d');
            
            this.chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [], // Will be populated with time labels
                    datasets: [
                        {
                            label: 'Requests per Hour',
                            data: [],
                            borderColor: '#2563eb',
                            backgroundColor: 'rgba(37, 99, 235, 0.1)',
                            tension: 0.4,
                            fill: true
                        },
                        {
                            label: 'Average Response Time (ms)',
                            data: [],
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            tension: 0.4,
                            fill: false,
                            yAxisID: 'y1'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        title: {
                            display: false
                        },
                        legend: {
                            position: 'top',
                        },
                        tooltip: {
                            callbacks: {
                                title: function(tooltipItems) {
                                    return tooltipItems[0].label;
                                },
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label) {
                                        label += ': ';
                                    }
                                    if (context.parsed.y !== null) {
                                        if (context.dataset.label.includes('Response Time')) {
                                            label += context.parsed.y + ' ms';
                                        } else {
                                            label += context.parsed.y.toLocaleString();
                                        }
                                    }
                                    return label;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: 'hour',
                                displayFormats: {
                                    hour: 'HH:mm'
                                }
                            },
                            title: {
                                display: true,
                                text: 'Time'
                            }
                        },
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Requests'
                            }
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Response Time (ms)'
                            },
                            grid: {
                                drawOnChartArea: false,
                            },
                        }
                    }
                }
            });

            // Initial chart data load
            this.updateChartData();

        } catch (error) {
            console.error('Error initializing chart:', error);
            if (chartCanvas.parentElement) {
                chartCanvas.parentElement.innerHTML = '<div class="error-message">Chart initialization failed</div>';
            }
        }
    }

    /**
     * Update chart data from analytics API
     */
    async updateChartData() {
        try {
            const timeRange = document.getElementById('chart-time-range')?.value || '24h';
            const response = await fetch(`/api/analytics/dashboard?hours=${this.parseTimeRange(timeRange)}`);
            const data = await response.json();

            if (this.chart && data.charts && data.charts.events_by_hour) {
                const chartData = data.charts.events_by_hour;
                
                // Update chart data
                this.chart.data.labels = chartData.map(item => new Date(item.hour));
                this.chart.data.datasets[0].data = chartData.map(item => item.count || 0);
                
                // Update response time data if available
                if (data.charts.response_times_by_hour) {
                    this.chart.data.datasets[1].data = data.charts.response_times_by_hour.map(item => item.avg_response_time || 0);
                }

                this.chart.update('none'); // Update without animation for performance
            }
        } catch (error) {
            console.error('Error updating chart data:', error);
        }
    }

    /**
     * Update recent activity feed
     */
    async updateActivityFeed() {
        const feedElement = document.getElementById('activity-feed');
        if (!feedElement) return;

        try {
            const response = await fetch('/api/analytics/events?limit=10');
            const data = await response.json();

            if (data && data.events && Array.isArray(data.events)) {
                const activitiesHtml = data.events.map(event => `
                    <div class="activity-item">
                        <div class="activity-icon">
                            <i class="fas ${this.getActivityIcon(event.event)}" aria-hidden="true"></i>
                        </div>
                        <div class="activity-content">
                            <span class="activity-text">
                                ${this.formatActivityText(event)}
                            </span>
                            <span class="activity-time">
                                ${this.formatTimeAgo(event.timestamp)}
                            </span>
                        </div>
                    </div>
                `).join('');

                feedElement.innerHTML = activitiesHtml || '<div class="no-data">No recent activity</div>';
            } else {
                feedElement.innerHTML = '<div class="no-data">No activity data available</div>';
            }
        } catch (error) {
            console.error('Error updating activity feed:', error);
            feedElement.innerHTML = '<div class="error-message">Failed to load activities</div>';
        }
    }

    /**
     * Start auto-refresh for dashboard data
     */
    startAutoRefresh() {
        // Clear existing interval if any
        if (this.intervalId) {
            clearInterval(this.intervalId);
        }

        // Set up new refresh interval
        this.intervalId = setInterval(async () => {
            try {
                await Promise.all([
                    this.loadSystemStatus(),
                    this.loadProviderStatus(),
                    this.updateChartData(),
                    this.updateActivityFeed()
                ]);

                // Update current time display
                this.updateCurrentTime();

                // Track auto-refresh for analytics
                if (window.AIAggregator) {
                    window.AIAggregator.trackFeature('dashboard_auto_refresh');
                }

            } catch (error) {
                console.error('Error during auto-refresh:', error);
                this.showError('Failed to refresh dashboard data');
            }
        }, this.updateInterval);

        console.log(`Dashboard auto-refresh started (${this.updateInterval / 1000}s interval)`);
    }

    /**
     * Stop auto-refresh
     */
    stopAutoRefresh() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            console.log('Dashboard auto-refresh stopped');
        }
    }

    /**
     * Bind event listeners for dashboard interactions
     */
    bindEvents() {
        // Chart time range selector
        const timeRangeSelector = document.getElementById('chart-time-range');
        if (timeRangeSelector) {
            timeRangeSelector.addEventListener('change', (event) => {
                this.updateChartData();
                
                if (window.AIAggregator) {
                    window.AIAggregator.trackFeature('chart_time_range_changed', {
                        range: event.target.value
                    });
                }
            });
        }

        // Refresh button
        const refreshButton = document.getElementById('refresh-status-btn');
        if (refreshButton) {
            refreshButton.addEventListener('click', async () => {
                refreshButton.disabled = true;
                refreshButton.innerHTML = '<i class="fas fa-sync fa-spin" aria-hidden="true"></i> Refreshing...';
                
                try {
                    await this.refreshAllData();
                    this.showNotification('Dashboard refreshed successfully', 'success');
                } catch (error) {
                    this.showError('Failed to refresh dashboard');
                } finally {
                    refreshButton.disabled = false;
                    refreshButton.innerHTML = '<i class="fas fa-sync" aria-hidden="true"></i> Refresh';
                }

                if (window.AIAggregator) {
                    window.AIAggregator.trackFeature('manual_refresh_clicked');
                }
            });
        }

        // Export data button
        const exportButton = document.getElementById('export-data-btn');
        if (exportButton) {
            exportButton.addEventListener('click', () => {
                this.exportDashboardData();
                
                if (window.AIAggregator) {
                    window.AIAggregator.trackFeature('export_data_clicked');
                }
            });
        }

        // AI test button
        const testAIButton = document.getElementById('test-ai-btn');
        if (testAIButton) {
            testAIButton.addEventListener('click', () => {
                this.openAITestModal();
                
                if (window.AIAggregator) {
                    window.AIAggregator.trackFeature('ai_test_modal_opened');
                }
            });
        }

        // View all events button
        const viewAllEventsBtn = document.getElementById('view-all-events');
        if (viewAllEventsBtn) {
            viewAllEventsBtn.addEventListener('click', () => {
                window.location.href = '/analytics';
                
                if (window.AIAggregator) {
                    window.AIAggregator.trackFeature('view_all_events_clicked');
                }
            });
        }

        // Page visibility change - pause/resume auto-refresh
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopAutoRefresh();
                console.log('Dashboard paused (page hidden)');
            } else {
                this.startAutoRefresh();
                console.log('Dashboard resumed (page visible)');
            }
        });

        // Window beforeunload - cleanup
        window.addEventListener('beforeunload', () => {
            this.stopAutoRefresh();
        });
    }

    /**
     * Refresh all dashboard data manually
     */
    async refreshAllData() {
        await Promise.all([
            this.loadSystemStatus(),
            this.loadProviderStatus(),
            this.loadAnalytics(),
            this.updateChartData(),
            this.updateActivityFeed()
        ]);

        this.updateCurrentTime();
    }

    /**
     * Update current time display
     */
    updateCurrentTime() {
        const timeElement = document.getElementById('current-time');
        if (timeElement) {
            const now = new Date();
            timeElement.textContent = now.toISOString().replace('T', ' ').slice(0, 19);
        }
    }

    /**
     * Export dashboard data to CSV
     */
    async exportDashboardData() {
        try {
            this.showNotification('Preparing export...', 'info');

            const response = await fetch('/api/analytics/export');
            const blob = await response.blob();
            
            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `dashboard-export-${new Date().toISOString().slice(0, 19)}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            this.showNotification('Data exported successfully', 'success');

        } catch (error) {
            console.error('Export failed:', error);
            this.showError('Failed to export data');
        }
    }

    /**
     * Open AI test modal
     */
    openAITestModal() {
        const modal = document.getElementById('ai-test-modal');
        if (modal && window.modalManager) {
            window.modalManager.show('ai-test-modal');
        }
    }

    // Utility functions

    /**
     * Format uptime duration
     * @param {number} milliseconds - Uptime in milliseconds
     * @returns {string} Formatted uptime string
     */
    formatUptime(milliseconds) {
        const seconds = Math.floor(milliseconds / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) {
            return `${days}d ${hours % 24}h`;
        } else if (hours > 0) {
            return `${hours}h ${minutes % 60}m`;
        } else {
            return `${minutes}m ${seconds % 60}s`;
        }
    }

    /**
     * Calculate requests per minute from health data
     * @param {Object} data - Health data
     * @returns {number} Requests per minute
     */
    calculateRequestsPerMinute(data) {
        // Mock calculation - implement based on your actual metrics
        if (data.performance && data.performance.total_requests && data.performance.uptime_hours) {
            const totalRequests = data.performance.total_requests;
            const uptimeMinutes = data.performance.uptime_hours * 60;
            return Math.round(totalRequests / uptimeMinutes);
        }
        return 0;
    }

    /**
     * Calculate error rate from health data
     * @param {Object} data - Health data
     * @returns {number} Error rate percentage
     */
    calculateErrorRate(data) {
        if (data.errors && data.errors.length > 0) {
            // Simple calculation based on error count vs total operations
            const errorCount = data.errors.length;
            const totalOperations = 100; // Mock value - implement based on actual data
            return Math.round((errorCount / totalOperations) * 100);
        }
        return 0;
    }

    /**
     * Get provider status CSS class
     * @param {string} status - Provider status
     * @returns {string} CSS class name
     */
    getProviderStatusClass(status) {
        switch (status?.toLowerCase()) {
            case 'healthy':
            case 'active':
            case 'online':
                return 'status-healthy';
            case 'warning':
            case 'degraded':
                return 'status-warning';
            case 'error':
            case 'offline':
            case 'failed':
                return 'status-error';
            default:
                return 'status-loading';
        }
    }

    /**
     * Get activity icon based on event type
     * @param {string} eventType - Type of event
     * @returns {string} FontAwesome icon class
     */
    getActivityIcon(eventType) {
        const iconMap = {
            'ai_request': 'fa-brain',
            'page_view': 'fa-eye',
            'error': 'fa-exclamation-triangle',
            'feature_usage': 'fa-mouse-pointer',
            'provider_change': 'fa-cogs',
            'user_action': 'fa-user',
            'system_event': 'fa-server',
            'default': 'fa-info-circle'
        };

        return iconMap[eventType] || iconMap.default;
    }

    /**
     * Format activity text for display
     * @param {Object} event - Event object
     * @returns {string} Formatted activity text
     */
    formatActivityText(event) {
        const eventType = event.event;
        const properties = event.properties || {};

        switch (eventType) {
            case 'ai_request':
                return `AI request to ${properties.provider || 'unknown'} provider`;
            case 'page_view':
                return `Page visited: ${properties.page || 'unknown'}`;
            case 'error':
                return `Error occurred: ${properties.message || 'Unknown error'}`;
            case 'feature_usage':
                return `Feature used: ${properties.feature || 'unknown'}`;
            default:
                return `${eventType.replace('_', ' ')} event`;
        }
    }

    /**
     * Format time ago string
     * @param {string} timestamp - ISO timestamp
     * @returns {string} Time ago string
     */
    formatTimeAgo(timestamp) {
        const now = new Date();
        const eventTime = new Date(timestamp);
        const diffMs = now - eventTime;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffDays > 0) {
            return `${diffDays}d ago`;
        } else if (diffHours > 0) {
            return `${diffHours}h ago`;
        } else if (diffMins > 0) {
            return `${diffMins}m ago`;
        } else {
            return 'Just now';
        }
    }

    /**
     * Format number with commas
     * @param {number} num - Number to format
     * @returns {string} Formatted number
     */
    formatNumber(num) {
        return num.toLocaleString();
    }

    /**
     * Parse time range string to hours
     * @param {string} range - Time range string (e.g., '24h', '7d')
     * @returns {number} Hours
     */
    parseTimeRange(range) {
        const match = range.match(/^(\d+)([hdwm])$/);
        if (!match) return 24;

        const value = parseInt(match[1]);
        const unit = match[2];

        switch (unit) {
            case 'h': return value;
            case 'd': return value * 24;
            case 'w': return value * 24 * 7;
            case 'm': return value * 24 * 30;
            default: return 24;
        }
    }

    /**
     * Escape HTML to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Show error notification
     * @param {string} message - Error message
     */
    showError(message) {
        if (window.AIAggregator && window.AIAggregator.showNotification) {
            window.AIAggregator.showNotification(message, 'error');
        } else {
            console.error(message);
        }
    }

    /**
     * Show success notification
     * @param {string} message - Success message
     * @param {string} type - Notification type
     */
    showNotification(message, type = 'info') {
        if (window.AIAggregator && window.AIAggregator.showNotification) {
            window.AIAggregator.showNotification(message, type);
        } else {
            console.log(message);
        }
    }

    /**
     * Cleanup dashboard resources
     */
    destroy() {
        this.stopAutoRefresh();
        
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }

        console.log('Dashboard destroyed');
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Global dashboard instance
    window.dashboard = new Dashboard();
    
    console.log('Dashboard initialized successfully');
    
    // Track dashboard initialization
    if (window.AIAggregator) {
        window.AIAggregator.trackFeature('dashboard_initialized', {
            user: 'AdsTable',
            timestamp: new Date().toISOString()
        });
    }
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Dashboard;
}