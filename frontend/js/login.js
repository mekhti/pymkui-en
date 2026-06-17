document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    const loginBtn = document.getElementById('loginBtn');
    const btnText = loginBtn.querySelector('.btn-text');
    const btnLoading = loginBtn.querySelector('.btn-loading');
    const secretInput = document.getElementById('secret');
    const togglePasswordBtn = document.getElementById('togglePassword');

    const serverUrl = window.location.origin;

    // Check whether already logged in
    checkAuth().then(isAuth => {
        if (isAuth) {
            showToast('Auto-logged in', 'success');
            setTimeout(() => {
                window.location.href = 'index.html';
            }, 1000);
        }
    });

    togglePasswordBtn.addEventListener('click', function() {
        const type = secretInput.getAttribute('type') === 'password' ? 'text' : 'password';
        secretInput.setAttribute('type', type);
        const icon = this.querySelector('i');
        if (type === 'password') {
            icon.className = 'fa fa-eye text-xl';
        } else {
            icon.className = 'fa fa-eye-slash text-xl';
        }
    });

    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const secret = secretInput.value.trim();

        if (!secret) {
            showToast('Enter API key', 'warning');
            return;
        }

        setLoading(true);

        try {
            const result = await Api.login(secret, serverUrl);

            if (result.success) {
                showToast('Login successful', 'success');
                setTimeout(() => {
                    window.location.href = 'index.html';
                }, 1000);
            } else {
                showToast(result.msg || 'Login failed', 'error');
            }
        } catch (error) {
            showToast('Login request failed: ' + error.message, 'error');
        } finally {
            setLoading(false);
        }
    });

    function setLoading(loading) {
        if (loading) {
            loginBtn.disabled = true;
            btnText.style.display = 'none';
            btnLoading.style.display = 'flex';
        } else {
            loginBtn.disabled = false;
            btnText.style.display = 'flex';
            btnLoading.style.display = 'none';
        }
    }
});

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    
    toast.textContent = message;
    
    // Remove all type classes
    toast.className = 'fixed top-5 right-5 z-50 px-6 py-4 rounded-xl text-white font-semibold shadow-xl backdrop-blur-lg transform translate-x-full opacity-0 transition-all duration-500 ease-out';
    
    // Add type class
    let bgClass = '';
    switch (type) {
        case 'success':
            bgClass = 'bg-gradient-to-r from-green-400 to-emerald-500';
            break;
        case 'error':
            bgClass = 'bg-gradient-to-r from-rose-500 to-red-500';
            break;
        case 'warning':
            bgClass = 'bg-gradient-to-r from-amber-400 to-yellow-500';
            break;
        default:
            bgClass = 'bg-gradient-primary';
    }
    
    toast.classList.add(...bgClass.split(' '));
    
    // Show toast
    setTimeout(() => {
        toast.classList.remove('translate-x-full', 'opacity-0');
    }, 100);
    
    // 3 seconds, then hide
    setTimeout(() => {
        toast.classList.add('translate-x-full', 'opacity-0');
    }, 3000);
}
