window.addEventListener('load', async () => {
  const loading = document.getElementById('loginLoading');
  const status = document.getElementById('loginStatus');

  try {
    if (!window.Clerk) {
      throw new Error('Secure sign-in failed to load. Refresh the page to try again.');
    }

    await Clerk.load({ ui: { ClerkUI: window.__internal_ClerkUICtor } });
    if (Clerk.isSignedIn) {
      window.location.replace(LOGIN_NEXT);
      return;
    }

    loading.style.display = 'none';
    Clerk.addListener(({ session }) => {
      if (session) {
        window.location.replace(LOGIN_NEXT);
      }
    });
    Clerk.mountSignIn(document.getElementById('clerkSignIn'), {
      fallbackRedirectUrl: LOGIN_NEXT,
      signUpFallbackRedirectUrl: LOGIN_NEXT,
    });
  } catch (error) {
    loading.style.display = 'none';
    status.textContent = error.message;
    status.className = 'status bad';
  }
});
