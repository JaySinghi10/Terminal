// ── SIGN IN WITH GOOGLE, AND IT IS NO LONGER ONE SCREEN'S ───────────────────
//
// THE REQUEST, THE EXCHANGE AND THE WEB FALLBACK moved here from Home when the
// profile became a route of its own. The sheet's "Sign in with Google" row,
// Home's inline button and Home's Gmail pull row all start the same flow, and
// a hook on Home cannot be reached from a screen the root Stack presents over
// it. Every line of the flow is what it was on Home; what changed is who can
// call it.
//
// ONE MOUNT, AT THE ROOT, AND IT USED TO BE ONE PER SCREEN. This was a hook,
// and every screen that called it built its own Google.useAuthRequest -- its own
// PKCE verifier, its own response, its own exchange effect. That was defensible
// at two consumers and stopped being so at four, when the Gmail pull began
// reaching for sign-in from My Flights and the search screen as well: four
// requests are built on every launch, four effects watch four responses, and
// which of them a prompt answers is decided by which one called promptAsync.
//
// A PROVIDER MAKES THAT STRUCTURAL RATHER THAN CAREFUL. One request exists
// because one provider is mounted, and the call sites did not change -- the hook
// keeps its name and reads a context instead of building anything. See
// app/_layout.tsx for where it is mounted and why it sits inside ToastProvider.
//
// WHAT HOME USED TO DO AFTER A SIGN-IN -- reset the Gmail pull and close an
// open card -- is not here. setEmail is the account-change signal every screen
// watches, and Home does both through useAccountChange now, the way the search
// screen has always cleared its own query.
import { createContext, useContext, useEffect, useEffectEvent, type ReactNode } from 'react';
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import * as Google from 'expo-auth-session/providers/google';
import { ResponseType } from 'expo-auth-session';
import { useAccount } from './account';
import { useSaved, API_BASE } from './saved';
import { useToast } from './toast';

type GoogleSignInValue = { signIn: () => void };

const GoogleSignInContext = createContext<GoogleSignInValue | null>(null);

export function GoogleSignInProvider({ children }: { children: ReactNode }) {
  const { persistUsername, persistSession } = useAccount();
  const { setEmail } = useSaved();
  const { showToast } = useToast();

  const [request, response, promptAsync] = Google.useAuthRequest({
    webClientId: '970706733452-n7ki9no870k7ad1bpkb86eu7rec0an7d.apps.googleusercontent.com',
    iosClientId: '970706733452-fmqtgg1doc0n14g8ibb8qsrsmcaot83e.apps.googleusercontent.com',
    androidClientId: '970706733452-n7ki9no870k7ad1bpkb86eu7rec0an7d.apps.googleusercontent.com',
    redirectUri: 'com.googleusercontent.apps.970706733452-fmqtgg1doc0n14g8ibb8qsrsmcaot83e:/oauth2redirect',
    scopes: ['profile', 'email', 'https://www.googleapis.com/auth/gmail.readonly'],
    // THE CODE FLOW, AND THE PHONE NEVER EXCHANGES THE CODE. It goes to our
    // server with the PKCE verifier, the server exchanges it and keeps the
    // refresh token (auth.py). shouldAutoExchangeCode is what stops this
    // library doing the exchange itself the moment the code arrives.
    // access_type=offline asks for a refresh token; prompt=consent makes
    // Google issue one even to an account that consented before, which is
    // exactly the account that signed in under the old flow.
    responseType: ResponseType.Code,
    shouldAutoExchangeCode: false,
    usePKCE: true,
    extraParams: { access_type: 'offline', prompt: 'consent' },
  });

  // AN EVENT, NOT A DEPENDENCY. The exchange reads the request, the persists
  // and setEmail as they are when the response lands, and none of them is a
  // reason to run it again: the response is the one trigger, below.
  const exchange = useEffectEvent(async () => {
    const code = response?.type === 'success' ? response.params?.code : undefined;
    const verifier = request?.codeVerifier;
    const redirectUri = request?.redirectUri;
    if (!code || !verifier || !redirectUri) return;
    try {
      // THE EXCHANGE HAPPENS ON OUR SERVER. It answers with a session, the
      // email and a first name -- read once from Google's id token and not
      // stored there -- so the app never calls Google's userinfo endpoint,
      // and never sees a Google token at all.
      const resp = await fetch(`${API_BASE}/auth/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, code_verifier: verifier, redirect_uri: redirectUri }),
      });
      const data = await resp.json() as {
        error?: string | null; code?: string | null; session?: string | null;
        email?: string | null; name?: string | null; gmail?: boolean;
      };
      if (!resp.ok || data.error || !data.session) {
        showToast(data.error || 'sign-in did not complete');
        return;
      }
      const validEmail = typeof data.email === 'string' && data.email.trim() ? data.email : null;
      const name = (typeof data.name === 'string' && data.name.trim())
        ? data.name.trim()
        : (validEmail ? (validEmail.split('@')[0].match(/^[a-zA-Z]+/)?.[0] ?? 'user') : 'user');
      // THE STORE WRITES KEEP THEIR ORDER: username, session, email, and
      // setEmail last, because setEmail is the account-change signal every
      // other screen watches and the stores must be current before it
      // fires. persistUsername writes and sets together, so the name state
      // is set here rather than after the email write; nothing reads it in
      // between.
      await persistUsername(name);
      // The session is lib/account.tsx's: the search screen sends it to
      // /chat and cannot see any screen's state, and that module writes
      // and sets together so a caller cannot do one without the other.
      await persistSession(data.session);
      if (validEmail) await SecureStore.setItemAsync('email', validEmail);
      if (validEmail) setEmail(validEmail);
      if (data.gmail === false) showToast('gmail access was not granted');
      // displayName is null here, so the profile sheet asks for one: it is
      // either already open, or Home opens it. See app/profile.tsx.
    } catch (err) {
      console.log('[Auth] exchange error:', err);
      showToast('sign-in did not complete');
    }
  });

  useEffect(() => {
    console.log('[Auth] response:', JSON.stringify(response));
    if (response?.type !== 'success') return;
    void exchange();
  }, [response]);

  // THE WEB PATH IS UNCHANGED, and still not the phone's. Google's identity
  // script is appended once and its callback persists the same things the
  // native exchange does, in the same order.
  const onCredential = useEffectEvent((credentialResponse: any) => {
    const payload = JSON.parse(atob(credentialResponse.credential.split('.')[1]));
    const firstName = (payload.email as string).split('@')[0].match(/^[a-zA-Z]+/)?.[0] || 'user';
    const validEmail = typeof payload.email === 'string' && payload.email.trim() ? payload.email : null;
    // Same order as the native sign-in: name, email, then setEmail.
    void persistUsername(firstName);
    if (validEmail) localStorage.setItem('email', validEmail);
    if (validEmail) setEmail(validEmail);
  });

  // THE GUARD THAT USED TO BE HERE IS GONE WITH THE SECOND CONSUMER. A
  // module-level flag kept the script to one append while any number of hooks
  // could mount; one provider is the same guarantee made by construction, and a
  // flag defending against a case that can no longer arise is a flag the next
  // reader has to disprove.
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = () => {
      (window as any).google.accounts.id.initialize({
        client_id: '970706733452-n7ki9no870k7ad1bpkb86eu7rec0an7d.apps.googleusercontent.com',
        scope: 'profile email https://www.googleapis.com/auth/gmail.readonly',
        callback: (credentialResponse: any) => { onCredential(credentialResponse); },
      });
    };
    document.head.appendChild(script);
    return () => { document.head.removeChild(script); };
  }, []);

  // ONE ENTRY POINT for every button that says "Sign in with Google": the
  // identity prompt on web, the auth session on the phone.
  const signIn = () => {
    console.log('Google sign in tapped, platform: ' + Platform.OS);
    if (Platform.OS === 'web') {
      (window as any).google?.accounts?.id?.prompt();
    } else {
      promptAsync();
    }
  };

  // NOT MEMOISED, AND THAT IS NOT AN OVERSIGHT. This provider re-renders only
  // when its own request or response changes, which is a sign-in beginning or
  // ending -- twice in a session, not once a frame. The React Compiler is on
  // (app.json) and memoises what it can; a hand-written useMemo here would have
  // to list every value signIn closes over and would be one more thing to keep
  // in step for no measurable gain.
  return (
    <GoogleSignInContext.Provider value={{ signIn }}>
      {children}
    </GoogleSignInContext.Provider>
  );
}

// THE NAME THE SCREENS ALREADY CALL. It was the whole implementation and is now
// the reader, so index.tsx, profile.tsx and lib/gmailPull.tsx did not change a
// line between the two versions.
export function useGoogleSignIn(): GoogleSignInValue {
  const v = useContext(GoogleSignInContext);
  if (v === null) throw new Error('useGoogleSignIn must be called inside GoogleSignInProvider');
  return v;
}
