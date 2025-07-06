/**
 * Modal management system
 * @author AdsTable Team
 * @version 1.0.0
 */

class ModalManager {
    constructor() {
        this.activeModal = null;
        this.bindEvents();
    }

    /**
     * Show modal by ID
     * @param {string} modalId - Modal element ID
     */
    show(modalId) {
        const modal = document.getElementById(modalId);
        if (!modal) {
            console.error(`Modal with ID '${modalId}' not found`);
            return;
        }

        // Hide any currently active modal
        if (this.activeModal) {
            this.hide();
        }

        // Show new modal
        modal.classList.add('show');
        modal.setAttribute('aria-hidden', 'false');
        
        // Focus management
        const focusableElements = modal.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length > 0) {
            focusableElements[0].focus();
        }

        // Set as active
        this.activeModal = modal;

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        // Track modal opening
        if (window.AIAggregator) {
            window.AIAggregator.trackFeature('modal_opened', {
                modal_id: modalId
            });
        }
    }

    /**
     * Hide active modal
     */
    hide() {
        if (!this.activeModal) return;

        this.activeModal.classList.remove('show');
        this.activeModal.setAttribute('aria-hidden', 'true');
        
        // Restore body scroll
        document.body.style.overflow = '';

        // Track modal closing
        if (window.AIAggregator) {
            window.AIAggregator.trackFeature('modal_closed', {
                modal_id: this.activeModal.id
            });
        }

        this.activeModal = null;
    }

    /**
     * Bind modal event listeners
     */
    bindEvents() {
        // Close modal on overlay click
        document.addEventListener('click', (event) => {
            if (event.target.classList.contains('modal-overlay')) {
                this.hide();
            }
        });

        // Close modal on close button click
        document.addEventListener('click', (event) => {
            if (event.target.closest('.modal-close') || 
                event.target.closest('[data-modal-close]')) {
                this.hide();
            }
        });

        // Close modal on Escape key
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && this.activeModal) {
                this.hide();
            }
        });

        // Handle modal trigger buttons
        document.addEventListener('click', (event) => {
            const trigger = event.target.closest('[data-modal-target]');
            if (trigger) {
                const targetId = trigger.getAttribute('data-modal-target');
                this.show(targetId);
            }
        });
    }
}

// AI Test Modal specific functionality
class AITestModal {
    constructor() {
        this.form = document.getElementById('ai-test-form');
        this.providerSelect = document.getElementById('test-provider');
        this.promptTextarea = document.getElementById('test-prompt');
        this.resultsContainer = document.getElementById('test-results');
        this.runButton = document.getElementById('run-test-btn');

        this.bindEvents();
        this.loadProviders();
    }

    /**
     * Load available providers into select dropdown
     */
    async loadProviders() {
        try {
            const response = await fetch('/providers');
            const data = await response.json();

            if (this.providerSelect) {
                this.providerSelect.innerHTML = '<option value="">Select a provider...</option>';
                
                if (data.providers && Array.isArray(data.providers)) {
                    data.providers.forEach(provider => {
                        const option = document.createElement('option');
                        option.value = provider.name;
                        option.textContent = `${provider.name} (${provider.status || 'unknown'})`;
                        option.disabled = provider.status !== 'healthy';
                        this.providerSelect.appendChild(option);
                    });
                }
            }
        } catch (error) {
            console.error('Failed to load providers:', error);
            if (this.providerSelect) {
                this.providerSelect.innerHTML = '<option value="">Failed to load providers</option>';
            }
        }
    }

    /**
     * Bind form events
     */
    bindEvents() {
        if (this.form) {
            this.form.addEventListener('submit', (event) => {
                event.preventDefault();
                this.runTest();
            });
        }
    }

    /**
     * Run AI provider test
     */
    async runTest() {
        const provider = this.providerSelect?.value;
        const prompt = this.promptTextarea?.value;
        const detailed = document.getElementById('test-detailed')?.checked;

        if (!provider || !prompt) {
            window.showNotification('Please select a provider and enter a prompt', 'warning');
            return;
        }

        // Update UI
        this.runButton.disabled = true;
        this.runButton.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Testing...';
        
        // Show results container
        this.resultsContainer.style.display = 'block';
        this.resultsContainer.querySelector('.results-content').innerHTML = 
            '<div class="loading-placeholder">Running test...</div>';

        try {
            const startTime = Date.now();
            
            const response = await fetch('/ai/ask', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    prompt: prompt,
                    provider: provider,
                    include_metadata: detailed
                })
            });

            const result = await response.json();
            const endTime = Date.now();
            const responseTime = endTime - startTime;

            // Display results
            this.displayResults(result, responseTime, detailed);

            // Track test completion
            if (window.AIAggregator) {
                window.AIAggregator.trackAIRequest(provider, prompt, responseTime, response.ok);
            }

        } catch (error) {
            console.error('Test failed:', error);
            this.displayError(error.message);
        } finally {
            // Reset UI
            this.runButton.disabled = false;
            this.runButton.innerHTML = '<i class="fas fa-play" aria-hidden="true"></i> Run Test';
        }
    }

    /**
     * Display test results
     */
    displayResults(result, responseTime, detailed) {
        const resultsHtml = `
            <div class="test-result-success">
                <div class="result-header">
                    <h5>Test Successful</h5>
                    <span class="response-time">Response time: ${responseTime}ms</span>
                </div>
                <div class="result-response">
                    <h6>Response:</h6>
                    <div class="response-content">${escapeHtml(result.response || 'No response')}</div>
                </div>
                ${detailed ? this.formatDetailedResults(result) : ''}
            </div>
        `;

        this.resultsContainer.querySelector('.results-content').innerHTML = resultsHtml;
        window.showNotification('AI test completed successfully', 'success');
    }

    /**
     * Display error results
     */
    displayError(errorMessage) {
        const errorHtml = `
            <div class="test-result-error">
                <div class="result-header">
                    <h5>Test Failed</h5>
                </div>
                <div class="result-error">
                    <h6>Error:</h6>
                    <div class="error-content">${escapeHtml(errorMessage)}</div>
                </div>
            </div>
        `;

        this.resultsContainer.querySelector('.results-content').innerHTML = errorHtml;
        window.showNotification('AI test failed', 'error');
    }

    /**
     * Format detailed results
     */
    formatDetailedResults(result) {
        return `
            <div class="result-metadata">
                <h6>Metadata:</h6>
                <div class="metadata-grid">
                    <div class="metadata-item">
                        <span class="label">Provider:</span>
                        <span class="value">${escapeHtml(result.provider || 'Unknown')}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="label">Status:</span>
                        <span class="value">${escapeHtml(result.status || 'Unknown')}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="label">Mode:</span>
                        <span class="value">${escapeHtml(result.mode || 'Unknown')}</span>
                    </div>
                    <div class="metadata-item">
                        <span class="label">Timestamp:</span>
                        <span class="value">${escapeHtml(result.timestamp || 'Unknown')}</span>
                    </div>
                </div>
            </div>
        `;
    }
}

// Initialize modal system
document.addEventListener('DOMContentLoaded', function() {
    window.modalManager = new ModalManager();
    
    // Initialize AI test modal if present
    if (document.getElementById('ai-test-modal')) {
        window.aiTestModal = new AITestModal();
    }

    console.log('Modal system initialized');
});