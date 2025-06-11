/**
 * Main application JavaScript with global utilities
 * @author AdsTable Team
 * @version 1.0.0
 */

/**
 * Global notification system
 */
window.showNotification = function(message, type = 'info', duration = 5000) {
    const container = document.getElementById('notification-container');
    if (!container) return;

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <div class="notification-icon">
                <i class="fas ${getNotificationIcon(type)}" aria-hidden="true"></i>
            </div>
            <div class="notification-message">${escapeHtml(message)}</div>
            <button class="notification-close" aria-label="Close notification">
                <i class="fas fa-times" aria-hidden="true"></i>
            </button>
        </div>
    `;

    // Add close button functionality
    notification.querySelector('.notification-close').addEventListener('click', () => {
        hideNotification(notification);
    });

    // Add to container
    container.appendChild(notification);

    // Show with animation
    setTimeout(() => notification.classList.add('show'), 10);

    // Auto-hide after duration
    if (duration > 0) {
        setTimeout(() => hideNotification(notification), duration);
    }

    return notification;
};

/**
 * Hide notification with animation
 */
function hideNotification(notification) {
    notification.classList.remove('show');
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 300);
}

/**
 * Get notification icon based on type
 */
function getNotificationIcon(type) {
    const icons = {
        'success': 'fa-check-circle',
        'error': 'fa-exclamation-circle',
        'warning': 'fa-exclamation-triangle',
        'info': 'fa-info-circle'
    };
    return icons[type] || icons.info;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Global loading overlay management
 */
window.loadingManager = {
    show: function(message = 'Loading...') {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            const messageElement = overlay.querySelector('p');
            if (messageElement) {
                messageElement.textContent = message;
            }
            overlay.classList.remove('hidden');
        }
    },

    hide: function() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.classList.add('hidden');
        }
    }
};

// Hide loading overlay when page is fully loaded
window.addEventListener('load', function() {
    setTimeout(() => {
        window.loadingManager.hide();
    }, 500);
});

// Initialize common functionality
document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle
    const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
    const sidebar = document.querySelector('.sidebar');
    
    if (mobileMenuToggle && sidebar) {
        mobileMenuToggle.addEventListener('click', function() {
            sidebar.classList.toggle('show');
            this.setAttribute('aria-expanded', sidebar.classList.contains('show'));
        });
    }

    // User menu toggle
    const userMenuToggle = document.querySelector('.user-menu-toggle');
    const userDropdown = document.querySelector('.user-dropdown');
    
    if (userMenuToggle && userDropdown) {
        userMenuToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            userDropdown.classList.toggle('show');
            this.setAttribute('aria-expanded', userDropdown.classList.contains('show'));
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', function() {
            userDropdown.classList.remove('show');
            userMenuToggle.setAttribute('aria-expanded', 'false');
        });
    }

    // Initialize current time update
    updateCurrentTime();
    setInterval(updateCurrentTime, 1000);

    console.log('Main application initialized');
});

/**
 * Update current time display
 */
function updateCurrentTime() {
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        const now = new Date();
        timeElement.textContent = now.toISOString().replace('T', ' ').slice(0, 19);
    }
}