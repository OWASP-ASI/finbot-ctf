/**
 * Global Agreement Check Script
 * Include this script on all protected pages to enforce user agreement
 */

(function () {
    'use strict';

    // List of pages that don't require agreement check
    const exemptPages = [
        '/agreement',
    ];

    // Check if current page is exempt
    function isExemptPage() {
        const currentPath = window.location.pathname;
        return exemptPages.some(page => currentPath.endsWith(page) || currentPath === page);
    }

    // Check if user has agreed to rules
    function hasUserAgreed() {
        // Check localStorage first
        const localStorageAgreed = localStorage.getItem('agreedToRules') === 'yes';

        // Check cookie as backup
        const cookieAgreed = document.cookie
            .split('; ')
            .find(row => row.startsWith('agreedToRules='))
            ?.split('=')[1] === 'yes';

        return localStorageAgreed || cookieAgreed;
    }

    // Redirect to entry page
    function redirectToEntry() {
        console.log('User agreement required - redirecting to entry page');
        window.location.href = '/agreement';
    }

    // Main agreement check function
    function checkAgreement() {
        // Skip check for exempt pages
        if (isExemptPage()) {
            return;
        }

        // Check if user has agreed
        if (!hasUserAgreed()) {
            redirectToEntry();
            return;
        }

        // User has agreed - continue with page load
        console.log('User agreement verified ✓');
    }

    // Run check when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkAgreement);
    } else {
        checkAgreement();
    }

    // Also run check immediately for safety
    checkAgreement();

})();


/**
 * Show CTF Details & Policy modal
 */
function showCTFDetailsModal() {
    // Create modal content
    const modalContent = `
        <div class="fixed inset-0 bg-black bg-opacity-50 z-[9999] flex items-center justify-center p-4">
            <div class="bg-gray-900 border border-green-400 rounded-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto">
                <div class="p-6">
                    <div class="flex items-center justify-between mb-6">
                        <div class="flex items-center space-x-3">
                            <div class="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-500 rounded-full flex items-center justify-center">
                                <svg class="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                                </svg>
                            </div>
                            <h2 class="text-xl font-bold text-green-400">FinBot - OWASP Agentic AI CTF Details & Policy</h2>
                        </div>
                        <button class="text-gray-400 hover:text-white" onclick="closeCTFModal()">
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                            </svg>
                        </button>
                    </div>

                    <div class="space-y-4 text-gray-300">
                        <div class="bg-green-900/20 border border-green-400/30 rounded-lg p-4">
                            <h3 class="text-green-400 font-semibold mb-2">🎯 CTF Objective</h3>
                            <p class="text-sm">This platform features FinBot, an AI-powered assistant designed for the OWASP Agentic AI Capture-the-Flag (CTF) experience. It explores real-world security risks, safe design practices, and behavior modeling in agentic systems.</p>
                        </div>

                        <div class="bg-blue-900/20 border border-blue-400/30 rounded-lg p-4">
                            <h3 class="text-blue-400 font-semibold mb-2">📋 Participation Policy</h3>
                            <ul class="text-sm space-y-1">
                                <li>• Use the system responsibly and for learning/testing purposes only</li>
                                <li>• Do not attempt to exploit, damage, or misuse the system beyond its intended CTF design</li>
                                <li>• Treat the system, data, and other users with respect</li>
                                <li>• Understand that interactions may be logged for educational and monitoring purposes</li>
                                <li>• Violations may result in access restrictions</li>
                            </ul>
                        </div>

                        <div class="bg-yellow-900/20 border border-yellow-400/30 rounded-lg p-4">
                            <h3 class="text-yellow-400 font-semibold mb-2">⚠️ Important Notices</h3>
                            <ul class="text-sm space-y-1">
                                <li>• All activities are logged and monitored</li>
                                <li>• This is a controlled environment for educational purposes only</li>
                                <li>• Malicious activities are prohibited</li>
                                <li>• Data may be reset periodically</li>
                            </ul>
                        </div>

                        <div class="bg-red-900/20 border border-red-400/30 rounded-lg p-4">
                            <h3 class="text-red-400 font-semibold mb-2">🛡️ Ethical Use Policy</h3>
                            <p class="text-sm">By using this CTF environment, you agree to use it ethically and responsibly. Any attempt to cause harm, access unauthorized systems, or violate the terms of use will result in immediate termination of access.</p>
                        </div>
                    </div>

                    <div class="mt-6 flex justify-end space-x-3">
                        <button onclick="window.open('https://genai.owasp.org/initiatives/#agenticinitiative', '_blank')" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors duration-300 flex items-center space-x-2">
                            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                            </svg>
                            <span>OWASP Initiative</span>
                        </button>
                        <button onclick="window.open('https://github.com/OWASP-ASI/finbot-ctf', '_blank')" class="bg-gray-700 hover:bg-gray-800 text-white px-4 py-2 rounded-lg transition-colors duration-300 flex items-center space-x-2">
                            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                            </svg>
                            <span>GitHub Repo</span>
                        </button>
                        <button onclick="closeCTFModal()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors duration-300">
                            Understood
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Add modal to page
    const modalDiv = document.createElement('div');
    modalDiv.id = 'ctf-modal';
    modalDiv.innerHTML = modalContent;
    document.body.appendChild(modalDiv);

    // Prevent body scroll
    document.body.style.overflow = 'hidden';
}

/**
 * Close CTF Details modal
 */
function closeCTFModal() {
    const modal = document.getElementById('ctf-modal');
    if (modal) {
        modal.remove();
        document.body.style.overflow = '';
    }
}

/**
 * Initialize CTF header functionality
 */
function initializeCTFHeader() {
    // CTF Details & Policy button functionality
    const ctfDetailsButton = document.querySelector('[data-ctf-details]');

    if (ctfDetailsButton) {
        ctfDetailsButton.addEventListener('click', () => {
            showCTFDetailsModal();
        });
    }
}

window.showCTFDetailsModal = showCTFDetailsModal;
window.closeCTFModal = closeCTFModal;
window.initializeCTFHeader = initializeCTFHeader;