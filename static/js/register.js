document.addEventListener('DOMContentLoaded', function() {
    const registerForm = document.getElementById('registerForm');
    
    // Переключение видимости пароля
    document.querySelectorAll('.toggle-password').forEach(toggle => {
        toggle.addEventListener('click', function() {
            const passwordInput = this.parentElement.querySelector('input');
            const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
            passwordInput.setAttribute('type', type);
            this.classList.toggle('fa-eye');
            this.classList.toggle('fa-eye-slash');
        });
    });

    // Валидация формы
    const validateForm = (formData) => {
        const errors = {};
        
        // Проверка имени пользователя
        if (formData.username.length < 3) {
            errors.username = 'Имя пользователя должно содержать минимум 3 символа';
        } else if (formData.username.length > 30) {
            errors.username = 'Имя пользователя не должно превышать 30 символов';
        } else if (!/^[a-zA-Z0-9_-]+$/.test(formData.username)) {
            errors.username = 'Имя пользователя может содержать только буквы, цифры, тире и подчеркивания';
        }
        
        // Проверка email
        if (!formData.email) {
            errors.email = 'Email обязателен';
        } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
            errors.email = 'Введите корректный email адрес';
        }
        
        // Проверка пароля
        if (formData.password.length < 8) {
            errors.password = 'Пароль должен содержать минимум 8 символов';
        } else if (!/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(formData.password)) {
            errors.password = 'Пароль должен содержать заглавные и строчные буквы, а также цифры';
        }

        // Проверка подтверждения пароля
        const confirmPassword = document.getElementById('confirmPassword').value;
        if (confirmPassword !== formData.password) {
            errors.confirmPassword = 'Пароли не совпадают';
        }
        
        return errors;
    };

    // Показ уведомления
    const showNotification = (type, title, message) => {
        // Удаляем предыдущие уведомления
        const existingNotifications = document.querySelectorAll('.notification');
        existingNotifications.forEach(notif => notif.remove());

        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = `
            <div class="notification-icon">
                <i class="fas ${type === 'error' ? 'fa-circle-xmark' : 'fa-triangle-exclamation'}"></i>
            </div>
            <div class="notification-content">
                <div class="notification-title">${title}</div>
                <div class="notification-message">${message}</div>
            </div>
            <button class="notification-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        document.body.appendChild(notification);
        setTimeout(() => notification.classList.add('show'), 10);
        
        // Автоматически скрываем через 5 секунд
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    };

    // Показ ошибок в форме
    const showFormErrors = (errors) => {
        // Очищаем предыдущие ошибки
        document.querySelectorAll('.form-error').forEach(error => error.remove());
        document.querySelectorAll('.error-input').forEach(input => input.classList.remove('error-input'));
        
        Object.entries(errors).forEach(([field, message]) => {
            const input = document.getElementById(field);
            const errorDiv = document.createElement('div');
            errorDiv.className = 'form-error';
            errorDiv.innerHTML = `
                <i class="fas fa-circle-exclamation"></i>
                ${message}
            `;
            
            input.classList.add('error-input');
            input.parentElement.appendChild(errorDiv);
        });
    };
    
    // Обработка отправки формы
    registerForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        // Получаем токен Turnstile
        const token = turnstile.getResponse();
        if (!token) {
            showNotification('warning', 'Подтверждение не пройдено', 'Пожалуйста, подтвердите, что вы не робот');
            return;
        }

        const formData = {
            username: document.getElementById('username').value.trim(),
            email: document.getElementById('email').value.trim(),
            password: document.getElementById('password').value,
            turnstileToken: token
        };

        // Клиентская валидация
        const errors = validateForm(formData);
        if (Object.keys(errors).length > 0) {
            showFormErrors(errors);
            return;
        }

        try {
            const response = await fetch('/api/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });
            
            const data = await response.json();
            
            if (response.ok) {
                showApiKeyModal(data.api_key);
            } else {
                const errorMessages = {
                    'username_exists': 'Пользователь с таким именем уже существует',
                    'email_exists': 'Этот email уже зарегистрирован',
                    'invalid_username': 'Недопустимое имя пользователя',
                    'invalid_email': 'Недопустимый email адрес',
                    'invalid_password': 'Недопустимый пароль',
                    'captcha_failed': 'Ошибка проверки капчи',
                    'validation_error': data.detail,
                    'database_error': 'Ошибка при создании пользователя',
                    'server_error': 'Внутренняя ошибка сервера'
                };

                const errorMessage = errorMessages[data.error_code] || data.detail || 'Произошла ошибка при регистрации';
                showNotification('error', 'Ошибка регистрации', errorMessage);
                
                if (data.error_code === 'captcha_failed') {
                    turnstile.reset();
                }
            }
        } catch (error) {
            console.error('Registration error:', error);
            showNotification('error', 'Ошибка сервера', 'Произошла ошибка при подключении к серверу. Пожалуйста, попробуйте позже.');
            turnstile.reset();
        }
    });

    // Очистка ошибок при вводе
    document.querySelectorAll('.form-group input').forEach(input => {
        input.addEventListener('input', function() {
            const errorDiv = this.parentElement.querySelector('.form-error');
            if (errorDiv) {
                errorDiv.remove();
            }
            this.classList.remove('error-input');
        });
    });
});

// Функция показа модального окна с API ключом
function showApiKeyModal(apiKey) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <h2>
                <i class="fas fa-check-circle success-icon"></i>
                Регистрация успешна!
            </h2>
            <p>Ваш API ключ готов к использованию</p>
            <div class="api-key-container">
                <code>${apiKey}</code>
                <button onclick="copyToClipboard('${apiKey}')" class="copy-btn" title="Скопировать API ключ">
                    <i class="fas fa-copy"></i>
                </button>
            </div>
            <p class="warning">
                <i class="fas fa-exclamation-triangle"></i>
                Сохраните этот ключ! Он будет показан только один раз.
            </p>
            <button onclick="window.location.href='/docs'" class="btn-register">Просмотреть документацию</button>
        </div>
    `;
    
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('active'), 50);
}

// Функция копирования в буфер обмена
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        const copyBtn = document.querySelector('.copy-btn');
        copyBtn.innerHTML = '<i class="fas fa-check"></i>';
        copyBtn.style.background = 'var(--accent)';
        copyBtn.style.color = 'var(--text)';
        
        setTimeout(() => {
            copyBtn.innerHTML = '<i class="fas fa-copy"></i>';
            copyBtn.style.background = 'var(--accent-light)';
            copyBtn.style.color = 'var(--accent)';
        }, 2000);
    });
}