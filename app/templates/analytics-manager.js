<!-- Add this script tag before closing </body> tag -->
<script src="/static/js/analytics-manager.js"></script>
<script>
// Initialize enhanced analytics tracking
document.addEventListener('DOMContentLoaded', function() {
    // Track page views
    robustAnalytics.track('page_view', {
        page: window.location.pathname,
        title: document.title,
        referrer: document.referrer
    });
    
    // Track AI requests (add to your existing AI request handling)
    function trackAIRequest(provider, prompt, responseTime) {
        robustAnalytics.track('ai_request', {
            provider: provider,
            prompt_length: prompt.length,
            response_time: responseTime,
            timestamp: new Date().toISOString()
        });
    }
    
    // Track errors (add to your existing error handling)
    window.addEventListener('error', function(event) {
        robustAnalytics.track('error', {
            error_type: 'javascript_error',
            message: event.message,
            filename: event.filename,
            line: event.lineno,
            column: event.colno
        });
    });
    
    // Track feature usage
    function trackFeatureUsage(feature, details = {}) {
        robustAnalytics.track('feature_usage', {
            feature: feature,
            ...details
        });
    }
    
    // Make functions globally available
    window.trackAIRequest = trackAIRequest;
    window.trackFeatureUsage = trackFeatureUsage;
});
</script>