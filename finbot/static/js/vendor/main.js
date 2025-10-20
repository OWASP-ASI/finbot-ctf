/**
 * FinBot Vendor Portal - Main JavaScript
 * Vendor-specific UI interactions and animations
 */

// Initialize portal when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    initializePortal();
    initializeAnimations();
    initializeInteractions();
    initializeCTFHeader();
});

/**
 * Initialize the main portal functionality
 */
function initializePortal() {
    // Create background elements
    createPortalBackground();
    createFloatingParticles();

    // Initialize components
    initializeNavigation();
    initializeMetrics();
    initializeForms();
    initializeChat();
}

/**
 * Create animated background grid
 */
function createPortalBackground() {
    const background = document.createElement('div');
    background.className = 'portal-background';
    document.body.appendChild(background);
}

/**
 * Create floating particles for ambient animation
 */
function createFloatingParticles() {
    const particleContainer = document.createElement('div');
    particleContainer.className = 'floating-particles';

    // Create 20 particles
    for (let i = 0; i < 20; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';

        // Random positioning
        particle.style.left = Math.random() * 100 + '%';
        particle.style.top = Math.random() * 100 + '%';
        particle.style.animationDelay = Math.random() * 6 + 's';
        particle.style.animationDuration = (Math.random() * 4 + 4) + 's';

        particleContainer.appendChild(particle);
    }

    document.body.appendChild(particleContainer);
}

/**
 * Initialize navigation interactions
 */
function initializeNavigation() {
    const navItems = document.querySelectorAll('.vendor-nav-item');

    navItems.forEach(item => {
        item.addEventListener('mouseenter', function () {
            this.style.transform = 'translateX(8px)';
        });

        item.addEventListener('mouseleave', function () {
            if (!this.classList.contains('active')) {
                this.style.transform = 'translateX(0)';
            }
        });
    });
}

/**
 * Initialize metric animations
 */
function initializeMetrics() {
    const metrics = document.querySelectorAll('.neural-metric');

    // Animate metrics on scroll
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animateMetricValue(entry.target);
            }
        });
    }, { threshold: 0.5 });

    metrics.forEach(metric => {
        observer.observe(metric);
    });
}

/**
 * Animate metric values with counting effect
 */
function animateMetricValue(metric) {
    const valueElement = metric.querySelector('.metric-value');
    if (!valueElement) return;

    const finalValue = parseInt(valueElement.textContent.replace(/[^\d]/g, ''));
    const duration = 2000;
    const steps = 60;
    const increment = finalValue / steps;
    let current = 0;

    const timer = setInterval(() => {
        current += increment;
        if (current >= finalValue) {
            current = finalValue;
            clearInterval(timer);
        }

        // Format the number with commas
        const formatted = Math.floor(current).toLocaleString();
        valueElement.textContent = formatted + (valueElement.textContent.includes('%') ? '%' : '');
    }, duration / steps);
}

/**
 * Initialize form interactions
 */
function initializeForms() {
    const inputs = document.querySelectorAll('.vendor-input, .neural-input');

    inputs.forEach(input => {
        // Add focus glow effect
        input.addEventListener('focus', function () {
            this.parentElement.style.boxShadow = '0 0 20px rgba(0, 212, 255, 0.3)';
        });

        input.addEventListener('blur', function () {
            this.parentElement.style.boxShadow = '';
        });

        // Add typing effect
        input.addEventListener('input', function () {
            if (this.value.length > 0) {
                this.style.borderColor = 'var(--vendor-accent)';
            } else {
                this.style.borderColor = 'rgba(0, 212, 255, 0.2)';
            }
        });
    });
}

/**
 * Initialize chat interface
 */
function initializeChat() {
    const chatInput = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendMessage');
    const chatMessages = document.getElementById('chatMessages');

    if (!chatInput || !sendButton || !chatMessages) return;

    // Auto-resize chat input
    chatInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = this.scrollHeight + 'px';
    });

    // Send message on Enter (but not Shift+Enter)
    chatInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    sendButton.addEventListener('click', sendChatMessage);
}

/**
 * Send chat message
 */
function sendChatMessage() {
    const chatInput = document.getElementById('chatInput');
    const message = chatInput.value.trim();

    if (!message) return;

    // Add user message
    addChatMessage(message, 'user');

    // Clear input
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Show typing indicator
    showTypingIndicator();

    // Simulate AI response
    setTimeout(() => {
        hideTypingIndicator();
        const response = generateAIResponse(message);
        addChatMessage(response, 'ai');
    }, 1500 + Math.random() * 1000);
}

/**
 * Add message to chat
 */
function addChatMessage(message, sender) {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'flex items-start space-x-3 mb-4 chat-message';

    if (sender === 'user') {
        messageDiv.innerHTML = `
            <div class="user-avatar flex-shrink-0">U</div>
            <div class="chat-bubble user">
                <p class="text-sm">${message}</p>
                <div class="text-xs opacity-60 mt-2">You • Just now</div>
            </div>
        `;
    } else {
        messageDiv.innerHTML = `
            <div class="chat-avatar flex-shrink-0">AI</div>
            <div class="chat-bubble ai">
                <p class="text-sm">${message}</p>
                <div class="text-xs opacity-60 mt-2">AI Assistant • Just now</div>
            </div>
        `;
    }

    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * Show typing indicator
 */
function showTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'flex items-start space-x-3 mb-4';
    typingDiv.id = 'typing-indicator';

    typingDiv.innerHTML = `
        <div class="chat-avatar flex-shrink-0">AI</div>
        <div class="chat-bubble ai">
            <div class="quantum-loader">
                <div class="quantum-dot"></div>
                <div class="quantum-dot"></div>
                <div class="quantum-dot"></div>
            </div>
        </div>
    `;

    chatMessages.appendChild(typingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

/**
 * Hide typing indicator
 */
function hideTypingIndicator() {
    const typingIndicator = document.getElementById('typing-indicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

/**
 * Generate AI response based on user input
 */
function generateAIResponse(userMessage) {
    const responses = [
        "I understand. Let me help you with that information.",
        "That's great! I'll process this data for your vendor profile.",
        "Perfect! This will help us match you with the right FinBot capabilities.",
        "Excellent choice. I'm updating your profile with this information.",
        "Thank you for providing that detail. What else can you tell me?",
        "I've noted that information. Let's continue with the next step.",
        "That's very helpful. I'm building your comprehensive vendor profile.",
        "Great! This information will help us provide better integration options."
    ];

    return responses[Math.floor(Math.random() * responses.length)];
}

/**
 * Initialize ambient animations
 */
function initializeAnimations() {
    // Parallax effect for background
    document.addEventListener('mousemove', function (e) {
        const mouseX = e.clientX / window.innerWidth;
        const mouseY = e.clientY / window.innerHeight;

        const background = document.querySelector('.portal-background');
        if (background) {
            background.style.transform = `translate(${mouseX * 10}px, ${mouseY * 10}px)`;
        }

        // Move particles slightly
        const particles = document.querySelectorAll('.particle');
        particles.forEach((particle, index) => {
            const speed = (index % 3 + 1) * 0.5;
            particle.style.transform = `translate(${mouseX * speed}px, ${mouseY * speed}px)`;
        });
    });

    // Animate cards on scroll
    const cards = document.querySelectorAll('.holo-card, .neural-metric');
    const cardObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, { threshold: 0.1 });

    cards.forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        cardObserver.observe(card);
    });
}

/**
 * Initialize interactive elements
 */
function initializeInteractions() {
    // Button hover effects
    const buttons = document.querySelectorAll('.vendor-btn');
    buttons.forEach(button => {
        button.addEventListener('mouseenter', function () {
            this.style.transform = 'translateY(-2px) scale(1.02)';
        });

        button.addEventListener('mouseleave', function () {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });

    // Card hover effects
    const holoCards = document.querySelectorAll('.holo-card');
    holoCards.forEach(card => {
        card.addEventListener('mouseenter', function () {
            this.style.transform = 'translateY(-4px) scale(1.01)';
        });

        card.addEventListener('mouseleave', function () {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });

    // Progress bar animations
    const progressBars = document.querySelectorAll('.progress-fill');
    const progressObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const bar = entry.target;
                const width = bar.getAttribute('data-width') || '0%';
                setTimeout(() => {
                    bar.style.width = width;
                }, 500);
            }
        });
    }, { threshold: 0.5 });

    progressBars.forEach(bar => {
        progressObserver.observe(bar);
    });
}

/**
 * Utility function to create status indicators
 */
function createStatusIndicator(status, text) {
    const indicator = document.createElement('span');
    indicator.className = `status-indicator ${status}`;
    indicator.textContent = text;
    return indicator;
}

/**
 * Utility function to create loading spinner
 */
function createLoadingSpinner() {
    const spinner = document.createElement('div');
    spinner.className = 'neural-spinner';
    return spinner;
}

// Export vendor-specific functions for use in templates
window.VendorPortal = {
    createStatusIndicator,
    createLoadingSpinner,
    addChatMessage
};