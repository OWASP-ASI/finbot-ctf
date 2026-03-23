/**
 * Vendor Onboarding Page Script
 * Handles form validation, auto-fill functionality, and submission
 */

ready(function() {
    CustomSelect.initAll();

    const onboardingForm = document.getElementById('onboardingForm');
    const submitButton = onboardingForm.querySelector('button[type="submit"]');

    // ==========================================
    // Auto-Fill Form Data
    // ==========================================
    const formFillerData = {
        companyPrefixes: ['Golden', 'Summit', 'Apex', 'Pacific', 'Atlantic', 'Paramount', 'Vista', 'Sterling', 'Prime', 'Eagle', 'Phoenix', 'Nova', 'Horizon', 'Zenith', 'Stellar'],
        companySuffixes: ['Solutions', 'Group', 'Technologies', 'Partners', 'Consulting', 'Systems', 'Services', 'Global', 'Dynamics', 'Industries'],
        firstNames: ['James', 'Sarah', 'Michael', 'Emily', 'David', 'Jessica', 'Robert', 'Ashley', 'William', 'Amanda', 'Richard', 'Stephanie', 'Thomas', 'Nicole', 'Christopher', 'Jennifer', 'Daniel', 'Elizabeth', 'Matthew', 'Lauren'],
        lastNames: ['Anderson', 'Mitchell', 'Thompson', 'Rodriguez', 'Martinez', 'Garcia', 'Wilson', 'Taylor', 'Moore', 'Jackson', 'White', 'Harris', 'Martin', 'Clark', 'Lewis', 'Robinson', 'Walker', 'Hall', 'Young', 'King'],
        domains: ['solutions.com', 'group.io', 'tech.co', 'services.net', 'consulting.com', 'systems.io', 'global.co'],
        bankNames: ['Chase Bank', 'Bank of America', 'Wells Fargo', 'Citibank', 'US Bank', 'PNC Bank', 'Capital One', 'TD Bank', 'Fifth Third Bank', 'Truist Bank'],
        categories: ['professional_services', 'technology_software', 'marketing_creative', 'facilities_operations', 'hr_staffing', 'logistics_supply_chain', 'financial_services', 'healthcare_life_sciences', 'manufacturing_engineering', 'construction_real_estate', 'security_compliance', 'catering_hospitality', 'other_specialized'],
        industries: ['fintech', 'banking', 'insurance', 'payments', 'lending', 'wealth', 'software_saas', 'information_technology', 'healthcare', 'manufacturing', 'retail', 'construction', 'energy', 'education', 'media_entertainment', 'consulting', 'government', 'other'],
        services: {
            professional_services: 'Expert consulting, advisory, and professional services including strategic planning, management consulting, accounting, auditing, and legal counsel for organizations across all sectors.',
            technology_software: 'Enterprise software and SaaS solutions including cloud platforms, workflow automation, data analytics, API integrations, developer tools, and custom application development.',
            marketing_creative: 'Full-service marketing and creative agency services including brand strategy, digital marketing, content creation, graphic design, advertising campaigns, and media buying.',
            facilities_operations: 'Comprehensive facilities management including building maintenance, cleaning services, office management, space planning, and operational support services.',
            hr_staffing: 'Human resources and staffing solutions including talent acquisition, temporary staffing, workforce planning, employee training, benefits administration, and HR consulting.',
            logistics_supply_chain: 'End-to-end logistics and supply chain management including freight forwarding, warehousing, inventory management, fleet operations, and last-mile delivery solutions.',
            financial_services: 'Financial services including payment processing, lending solutions, insurance products, wealth management, risk assessment, and financial technology integration.',
            healthcare_life_sciences: 'Healthcare and life sciences services including medical equipment supply, pharmaceutical distribution, clinical research support, health IT solutions, and biotech consulting.',
            manufacturing_engineering: 'Manufacturing and engineering services including precision machining, industrial design, quality assurance, raw material supply, and production line optimization.',
            construction_real_estate: 'Construction and real estate services including general contracting, architectural design, project management, property development, and building inspection.',
            security_compliance: 'Security and compliance services including physical security, cybersecurity assessments, governance risk and compliance, penetration testing, and regulatory consulting.',
            catering_hospitality: 'Catering and hospitality services including corporate event catering, food service management, event planning, travel coordination, and venue management.',
            other_specialized: 'Specialized services tailored to unique business requirements. Please describe your specific services and capabilities in detail.'
        }
    };

    function randomItem(arr) {
        return arr[Math.floor(Math.random() * arr.length)];
    }

    function generateCompanyName() {
        return `${randomItem(formFillerData.companyPrefixes)} ${randomItem(formFillerData.companySuffixes)}`;
    }

    function generatePersonName() {
        return `${randomItem(formFillerData.firstNames)} ${randomItem(formFillerData.lastNames)}`;
    }

    function generateEmail(companyName, personName) {
        const cleanCompany = companyName.toLowerCase().replace(/\s+/g, '');
        const firstName = personName.split(' ')[0].toLowerCase();
        const domain = randomItem(formFillerData.domains);
        return `${firstName}@${cleanCompany.substring(0, 12)}.${domain.split('.')[1]}`;
    }

    function generatePhone() {
        const areaCodes = ['212', '310', '415', '404', '312', '305', '617', '702', '818', '323'];
        const areaCode = randomItem(areaCodes);
        const exchange = Math.floor(Math.random() * 900) + 100;
        const subscriber = Math.floor(Math.random() * 9000) + 1000;
        return `(${areaCode}) ${exchange}-${subscriber}`;
    }

    function generateTIN() {
        // Generate valid format EIN: XX-XXXXXXX
        const prefix = Math.floor(Math.random() * 90) + 10;
        const suffix = Math.floor(Math.random() * 9000000) + 1000000;
        return `${prefix}-${suffix}`;
    }

    function generateBankAccount() {
        // Generate 10-12 digit account number
        const length = Math.floor(Math.random() * 3) + 10;
        let account = '';
        for (let i = 0; i < length; i++) {
            account += Math.floor(Math.random() * 10);
        }
        return account;
    }

    function generateRoutingNumber() {
        // Generate valid 9-digit routing number format
        // Using common valid routing number prefixes
        const prefixes = ['021', '026', '031', '041', '051', '061', '071', '081', '091', '101', '111', '121'];
        const prefix = randomItem(prefixes);
        let suffix = '';
        for (let i = 0; i < 6; i++) {
            suffix += Math.floor(Math.random() * 10);
        }
        return prefix + suffix;
    }

    function autoFillForm() {
        const companyName = generateCompanyName();
        const personName = generatePersonName();
        const category = randomItem(formFillerData.categories);
        const industry = randomItem(formFillerData.industries);

        // Fill form fields
        document.getElementById('company_name').value = companyName;
        document.getElementById('vendor_category').value = category;
        document.getElementById('industry').value = industry;
        document.getElementById('name').value = personName;
        document.getElementById('email').value = generateEmail(companyName, personName);
        document.getElementById('phone').value = generatePhone();
        document.getElementById('tin').value = generateTIN();
        document.getElementById('bank_account_number').value = generateBankAccount();
        document.getElementById('bank_name').value = randomItem(formFillerData.bankNames);
        document.getElementById('bank_routing_number').value = generateRoutingNumber();
        document.getElementById('bank_account_holder_name').value = companyName;
        document.getElementById('services').value = formFillerData.services[category];

        // Trigger change events for any listeners
        onboardingForm.querySelectorAll('input, select, textarea').forEach(field => {
            field.dispatchEvent(new Event('change', { bubbles: true }));
        });

        showNotification('Form auto-filled with sample data', 'success');
    }

    // Attach auto-fill button handler
    const autoFillBtn = document.getElementById('autoFillBtn');
    if (autoFillBtn) {
        autoFillBtn.addEventListener('click', autoFillForm);
    }

    // Add real-time email validation
    const emailField = document.getElementById('email');
    if (emailField) {
        emailField.addEventListener('blur', function() {
            const email = this.value.trim();
            if (email && !isValidEmail(email)) {
                showFieldError(this, 'Please enter a valid email address');
            } else {
                clearFieldError(this);
            }
        });
    }

    // Add phone number formatting
    const phoneField = document.getElementById('phone');
    if (phoneField) {
        phoneField.addEventListener('input', function() {
            // Simple phone formatting (US format)
            let value = this.value.replace(/\D/g, '');
            if (value.length >= 6) {
                value = value.replace(/(\d{3})(\d{3})(\d{4})/, '($1) $2-$3');
            } else if (value.length >= 3) {
                value = value.replace(/(\d{3})(\d{0,3})/, '($1) $2');
            }
            this.value = value;
        });
    }

    // Add TIN/EIN formatting
    const tinField = document.getElementById('tin');
    if (tinField) {
        tinField.addEventListener('blur', function() {
            if (this.value) {
                this.value = formatTIN(this.value);
            }
        });
    }

    // Add routing number formatting for display
    const routingField = document.getElementById('bank_routing_number');
    if (routingField) {
        routingField.addEventListener('blur', function() {
            if (this.value) {
                // Only format for display, keep actual value clean for validation
                const cleanValue = this.value.replace(/\D/g, '');
                if (cleanValue.length === 9) {
                    this.value = cleanValue; // Keep it clean for form submission
                }
            }
        });
    }

    // Enhanced form submission with validation
    onboardingForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        // Clear any existing errors
        clearAllFieldErrors(this);

        // Validate form using utils.js helper
        const validation = validateForm(this);

        if (!validation.isValid) {
            // Display validation errors
            Object.keys(validation.errors).forEach(fieldName => {
                const field = this.querySelector(`[name="${fieldName}"]`);
                if (field) {
                    showFieldError(field, validation.errors[fieldName][0]);
                }
            });

            showNotification('Please correct the errors below', 'error');
            return;
        }

        // Additional custom validations using utils.js functions
        const customValidation = performCustomValidations();
        if (!customValidation.isValid) {
            showNotification(customValidation.message, 'error');
            return;
        }

        const hideLoading = showLoading(submitButton, 'Processing Application...');

        try {
            // Submit form data to API
            const formData = new FormData(onboardingForm);
            const vendorData = {
                company_name: formData.get('company_name'),
                vendor_category: formData.get('vendor_category'),
                industry: formData.get('industry'),
                services: formData.get('services'),
                name: formData.get('name'),
                email: formData.get('email'),
                phone: formData.get('phone'),
                tin: formData.get('tin'),
                bank_account_number: formData.get('bank_account_number'),
                bank_name: formData.get('bank_name'),
                bank_routing_number: formData.get('bank_routing_number'),
                bank_account_holder_name: formData.get('bank_account_holder_name')
            };

            const response = await api.post('/vendor/api/v1/vendors/register', vendorData);

            // Success state
            submitButton.innerHTML = `
                <span class="text-lg font-semibold text-vendor-accent">✓ Application Submitted</span>
                <div class="text-xs opacity-80 mt-1">Vendor ID: ${response.data.vendor_id}</div>
            `;

            showNotification('Application submitted successfully! Redirecting to dashboard...', 'success');

            // Disable form after successful submission
            this.style.opacity = '0.7';
            this.style.pointerEvents = 'none';

            // Redirect to the dashboard
            setTimeout(() => {
                window.location.href = '/vendor/dashboard';
            }, 3000);

        } catch (error) {
            hideLoading();

            // Handle API errors using the global error handler
            const errorMessage = handleAPIError(error, { showAlert: true });

            // Only show notification for non-CSRF errors (CSRF errors are handled by handleAPIError)
            if (!(error.status === 403 && error.data?.error?.type === 'csrf_error')) {
                showNotification(`Failed to submit application: ${errorMessage}`, 'error');
            }

            console.error('Form submission error:', error);
        }
    });

    // Custom validation logic using utils.js functions
    function performCustomValidations() {
        const formData = new FormData(onboardingForm);
        let hasErrors = false;

        // Validate TIN/EIN using utils.js function
        const tin = formData.get('tin');
        if (tin) {
            const tinValidation = validateTIN(tin);
            if (!tinValidation.isValid) {
                const tinField = document.getElementById('tin');
                showFieldError(tinField, tinValidation.message);
                hasErrors = true;
            }
        }

        // Validate bank account number using utils.js function
        const bankAccount = formData.get('bank_account_number');
        if (bankAccount) {
            const bankValidation = validateBankAccount(bankAccount);
            if (!bankValidation.isValid) {
                const bankField = document.getElementById('bank_account_number');
                showFieldError(bankField, bankValidation.message);
                hasErrors = true;
            }
        }

        // Validate routing number using utils.js function
        const routingNumber = formData.get('bank_routing_number');
        if (routingNumber) {
            const routingValidation = validateRoutingNumber(routingNumber);
            if (!routingValidation.isValid) {
                const routingField = document.getElementById('bank_routing_number');
                showFieldError(routingField, routingValidation.message);
                hasErrors = true;
            }
        }

        return {
            isValid: !hasErrors,
            message: hasErrors ? 'Please correct the financial information errors' : ''
        };
    }

});
