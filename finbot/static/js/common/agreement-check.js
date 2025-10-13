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

