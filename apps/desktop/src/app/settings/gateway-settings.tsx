import { useStore } from '@nanostores/react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { DesktopAuthProvider, DesktopConnectionProbeResult } from '@/global'
import { useI18n } from '@/i18n'
import { AlertCircle, Check, FileText, Globe, Loader2, LogIn, Monitor, Network } from '@/lib/icons'
import { cn } from '@/lib/utils'
import { notify, notifyError } from '@/store/notifications'
import { $profiles, refreshActiveProfile } from '@/store/profile'

import { CONTROL_TEXT } from './constants'
import { EmptyState, ListRow, LoadingState, Pill, SettingsContent } from './primitives'

type Mode = 'local' | 'remote' | 'ssh'
type AuthMode = 'oauth' | 'token'
type ProbeStatus = 'idle' | 'probing' | 'done' | 'error'
type SshTestStatus = 'idle' | 'testing' | 'ok' | 'error'

interface GatewaySettingsState {
  envOverride: boolean
  mode: Mode
  remoteAuthMode: AuthMode
  remoteOauthConnected: boolean
  remoteTokenPreview: string | null
  remoteTokenSet: boolean
  remoteUrl: string
  sshHost: string
  sshUser: string
  sshPort: number | null
  sshKeyPath: string
  sshRemoteHermesPath: string
}

const EMPTY_STATE: GatewaySettingsState = {
  envOverride: false,
  mode: 'local',
  remoteAuthMode: 'token',
  remoteOauthConnected: false,
  remoteTokenPreview: null,
  remoteTokenSet: false,
  remoteUrl: '',
  sshHost: '',
  sshUser: '',
  sshPort: null,
  sshKeyPath: '',
  sshRemoteHermesPath: ''
}

function ModeCard({
  active,
  description,
  disabled,
  icon: Icon,
  onSelect,
  title
}: {
  active: boolean
  description: string
  disabled?: boolean
  icon: typeof Monitor
  onSelect: () => void
  title: string
}) {
  return (
    <button
      className={cn(
        'rounded-xl border p-3 text-left transition',
        active
          ? 'border-(--ui-stroke-secondary) bg-(--ui-bg-tertiary)'
          : 'border-(--ui-stroke-tertiary) bg-(--ui-bg-quinary) hover:bg-(--chrome-action-hover)',
        disabled && 'cursor-not-allowed opacity-50'
      )}
      disabled={disabled}
      onClick={onSelect}
      type="button"
    >
      <div className="flex items-center gap-2 text-[length:var(--conversation-text-font-size)] font-medium">
        <Icon className="size-4 text-muted-foreground" />
        <span>{title}</span>
        {active ? <Check className="ml-auto size-4 text-primary" /> : null}
      </div>
      <p className="mt-1.5 text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)">
        {description}
      </p>
    </button>
  )
}

function ScopeChip({ active, label, onSelect }: { active: boolean; label: string; onSelect: () => void }) {
  return (
    <button
      className={cn(
        'rounded-full border px-3 py-1 text-[length:var(--conversation-caption-font-size)] transition',
        active
          ? 'border-(--ui-stroke-secondary) bg-(--ui-bg-tertiary) text-(--ui-text-primary)'
          : 'border-(--ui-stroke-tertiary) bg-(--ui-bg-quinary) text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)'
      )}
      onClick={onSelect}
      type="button"
    >
      {label}
    </button>
  )
}

export function GatewaySettings() {
  const { t } = useI18n()
  const g = t.settings.gateway
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [signingIn, setSigningIn] = useState(false)
  const [state, setState] = useState<GatewaySettingsState>(EMPTY_STATE)
  const [remoteToken, setRemoteToken] = useState('')
  const [lastTest, setLastTest] = useState<null | string>(null)

  // SSH-mode local UI state: the connection test result, ~/.ssh/config host
  // suggestions, and the `ssh -G` resolution of the entered host.
  const [sshTestStatus, setSshTestStatus] = useState<SshTestStatus>('idle')
  const [sshTestMessage, setSshTestMessage] = useState<null | string>(null)
  const [sshHostSuggestions, setSshHostSuggestions] = useState<string[]>([])

  // Connection scope: null = the global/default connection (the original
  // behavior); a profile name = that profile's per-profile remote override, so
  // each profile can point at its own backend.
  const [scope, setScope] = useState<null | string>(null)
  const profiles = useStore($profiles)

  useEffect(() => {
    void refreshActiveProfile()
  }, [])

  // Auth-mode probe: as the user types a remote URL we ask the gateway (via
  // its public /api/status) whether it gates with OAuth or a static session
  // token, so we can show the right control (login button vs token box).
  const [probeStatus, setProbeStatus] = useState<ProbeStatus>('idle')
  const [probe, setProbe] = useState<DesktopConnectionProbeResult | null>(null)
  const probeSeq = useRef(0)

  useEffect(() => {
    let cancelled = false
    const desktop = window.hermesDesktop

    if (!desktop?.getConnectionConfig) {
      setLoading(false)

      return () => void (cancelled = true)
    }

    setLoading(true)
    // Clear scope-local entry state so a token from one scope can't leak into
    // the next when switching profiles.
    setRemoteToken('')
    setLastTest(null)

    desktop
      .getConnectionConfig(scope)
      .then(config => {
        if (cancelled) {
          return
        }

        setState(config)
      })
      .catch(err => notifyError(err, g.failedLoad))
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => void (cancelled = true)
  }, [scope])

  // Debounced probe of the entered remote URL. Only runs in remote mode with a
  // syntactically plausible URL. The probe result drives whether we render the
  // OAuth login button or the session-token entry box. The effective auth mode
  // prefers a fresh probe result over the saved value.
  const trimmedUrl = state.remoteUrl.trim()
  useEffect(() => {
    if (state.mode !== 'remote' || !trimmedUrl || !/^https?:\/\//i.test(trimmedUrl)) {
      setProbeStatus('idle')
      setProbe(null)

      return
    }

    const desktop = window.hermesDesktop

    if (!desktop?.probeConnectionConfig) {
      return
    }

    const seq = ++probeSeq.current
    setProbeStatus('probing')

    const timer = setTimeout(() => {
      desktop
        .probeConnectionConfig(trimmedUrl)
        .then(result => {
          if (seq !== probeSeq.current) {
            return
          }

          setProbe(result)
          setProbeStatus(result.reachable ? 'done' : 'error')
        })
        .catch(() => {
          if (seq !== probeSeq.current) {
            return
          }

          setProbe(null)
          setProbeStatus('error')
        })
    }, 500)

    return () => clearTimeout(timer)
  }, [state.mode, trimmedUrl])

  // Effective auth mode: a reachable probe wins; otherwise fall back to the
  // saved config's mode so a re-open of settings doesn't flicker.
  const authMode: AuthMode = useMemo(() => {
    if (probeStatus === 'done' && probe && probe.authMode !== 'unknown') {
      return probe.authMode
    }

    return state.remoteAuthMode
  }, [probe, probeStatus, state.remoteAuthMode])

  // Whether we actually KNOW how this gateway authenticates yet. Until we do,
  // neither the OAuth button nor the session-token box should render —
  // `authMode` defaults to 'token', so without this gate the token box flashes
  // for every gateway (including OAuth ones) during the idle/probing window
  // before the first probe lands. The scheme is known when either:
  //   * the live probe finished (probeStatus 'done'), or
  //   * we're idle but showing a previously-saved remote config (re-opening
  //     settings for a gateway already signed-in or with a saved token), so
  //     its control appears immediately with no flicker.
  // While probing (or after a probe error), the scheme is unknown and we show
  // the probe status row instead of a control.
  const hasSavedRemote = state.remoteTokenSet || state.remoteOauthConnected

  const authResolved = useMemo(() => {
    if (probeStatus === 'done') {
      return true
    }

    return probeStatus === 'idle' && hasSavedRemote
  }, [probeStatus, hasSavedRemote])

  const providerLabel = useMemo(() => {
    const providers: DesktopAuthProvider[] = probe?.providers ?? []

    if (providers.length === 1) {
      return providers[0].displayName || providers[0].name
    }

    if (providers.length > 1) {
      return providers.map(p => p.displayName || p.name).join(' / ')
    }

    return t.boot.failure.identityProvider
  }, [probe, t.boot.failure.identityProvider])

  // A username/password gateway authenticates through a credential form on the
  // gateway's /login page (POST /auth/password-login) rather than an OAuth
  // redirect. Everything downstream — the session cookie, the ws-ticket mint,
  // the persistent partition — is identical, so the desktop drives it through
  // the same sign-in window; only the button copy changes. We treat the
  // gateway as password-style only when EVERY advertised provider supports
  // password, so a mixed deployment keeps the generic OAuth copy.
  const isPasswordProvider = useMemo(() => {
    const providers: DesktopAuthProvider[] = probe?.providers ?? []

    return providers.length > 0 && providers.every(p => p.supportsPassword)
  }, [probe])

  // The 'default' profile uses the global ("All profiles") connection, so the
  // per-profile scopes are the named, non-default profiles.
  const namedProfiles = useMemo(() => profiles.filter(profile => profile.name !== 'default'), [profiles])

  // Load ~/.ssh/config host suggestions once SSH mode is active (read-only).
  useEffect(() => {
    if (state.mode !== 'ssh') return
    const desktop = window.hermesDesktop
    if (!desktop?.sshConfigHosts) return
    let cancelled = false
    desktop
      .sshConfigHosts()
      .then(result => {
        if (!cancelled) setSshHostSuggestions(result.hosts || [])
      })
      .catch(() => {
        if (!cancelled) setSshHostSuggestions([])
      })
    return () => void (cancelled = true)
  }, [state.mode])

  const oauthConnected = state.remoteOauthConnected

  const canUseRemote = useMemo(() => {
    if (!trimmedUrl) {
      return false
    }

    if (authMode === 'oauth') {
      return oauthConnected
    }

    return Boolean(remoteToken.trim()) || state.remoteTokenSet
  }, [authMode, oauthConnected, remoteToken, state.remoteTokenSet, trimmedUrl])

  const payload = () => ({
    mode: state.mode,
    profile: scope ?? undefined,
    remoteAuthMode: authMode,
    remoteToken: authMode === 'token' ? remoteToken.trim() || undefined : undefined,
    remoteUrl: trimmedUrl
  })

  const save = async (apply: boolean) => {
    if (state.mode === 'remote' && !canUseRemote) {
      notify({
        kind: 'warning',
        title: g.incompleteTitle,
        message:
          authMode === 'oauth'
            ? g.incompleteSignIn
            : g.incompleteToken
      })

      return
    }

    setSaving(true)

    try {
      const next = apply
        ? await window.hermesDesktop.applyConnectionConfig(payload())
        : await window.hermesDesktop.saveConnectionConfig(payload())

      setState(next)
      setRemoteToken('')
      notify({
        kind: 'success',
        title: apply ? g.restartingTitle : g.savedTitle,
        message: apply ? g.restartingMessage : g.savedMessage
      })
    } catch (err) {
      notifyError(err, apply ? g.applyFailed : g.saveFailed)
    } finally {
      setSaving(false)
    }
  }

  // OAuth sign-in: persist the URL + oauth mode first (so the saved config has
  // the URL the login window needs), then open the gateway login window and
  // refresh the connection status from the saved config once it completes.
  const signIn = async () => {
    if (!trimmedUrl) {
      notify({ kind: 'warning', title: g.incompleteTitle, message: g.enterUrlFirst })

      return
    }

    setSigningIn(true)

    try {
      // Save (don't apply/restart) so the login window has a URL to use and the
      // oauth mode is persisted, without yet flipping the live connection.
      const saved = await window.hermesDesktop.saveConnectionConfig({
        mode: state.mode,
        profile: scope ?? undefined,
        remoteAuthMode: 'oauth',
        remoteUrl: trimmedUrl
      })

      setState(saved)

      const result = await window.hermesDesktop.oauthLoginConnectionConfig(trimmedUrl)

      if (result.connected) {
        const refreshed = await window.hermesDesktop.getConnectionConfig(scope)
        setState(refreshed)
        notify({ kind: 'success', title: g.signedIn, message: g.connectedTo(providerLabel) })
      } else {
        notify({
          kind: 'warning',
          title: t.boot.failure.signInIncompleteTitle,
          message: t.boot.failure.signInIncompleteMessage
        })
      }
    } catch (err) {
      notifyError(err, g.signInFailed)
    } finally {
      setSigningIn(false)
    }
  }

  const signOut = async () => {
    setSigningIn(true)

    try {
      await window.hermesDesktop.oauthLogoutConnectionConfig(trimmedUrl || undefined)
      const refreshed = await window.hermesDesktop.getConnectionConfig(scope)
      setState(refreshed)
      notify({ kind: 'success', title: g.signedOutTitle, message: g.signedOutMessage })
    } catch (err) {
      notifyError(err, g.signOutFailed)
    } finally {
      setSigningIn(false)
    }
  }

  const testRemote = async () => {
    if (!canUseRemote) {
      notify({
        kind: 'warning',
        title: g.incompleteTitle,
        message:
          authMode === 'oauth'
            ? g.incompleteSignInTest
            : g.incompleteTokenTest
      })

      return
    }

    setTesting(true)
    setLastTest(null)

    try {
      const result = await window.hermesDesktop.testConnectionConfig({
        mode: 'remote',
        profile: scope ?? undefined,
        remoteAuthMode: authMode,
        remoteToken: authMode === 'token' ? remoteToken.trim() || undefined : undefined,
        remoteUrl: trimmedUrl
      })

      const message = g.connectedTo(result.baseUrl ?? trimmedUrl, result.version ?? undefined)
      setLastTest(message)
      notify({ kind: 'success', title: g.reachableTitle, message })
    } catch (err) {
      notifyError(err, g.testFailed)
    } finally {
      setTesting(false)
    }
  }

  // --- SSH mode -------------------------------------------------------------

  const canUseSsh = Boolean(state.sshHost.trim())

  const sshPayload = () => ({
    mode: 'ssh' as const,
    profile: scope ?? undefined,
    sshHost: state.sshHost.trim(),
    sshUser: state.sshUser.trim() || undefined,
    sshPort: state.sshPort ?? undefined,
    sshKeyPath: state.sshKeyPath.trim() || undefined,
    sshRemoteHermesPath: state.sshRemoteHermesPath.trim() || undefined
  })

  // Map an SSH test error kind to actionable copy.
  const sshErrorMessage = (kind: string | null | undefined, raw: string | null | undefined): string => {
    switch (kind) {
      case 'auth-failed':
        return g.sshErrAuth
      case 'unreachable':
        return g.sshErrUnreachable
      case 'host-key-changed':
        return g.sshErrHostKey
      case 'hermes-not-found':
        return g.sshErrNotInstalled
      case 'unsupported-platform':
        return g.sshErrPlatform
      case 'timeout':
        return g.sshErrTimeout
      default:
        return raw || g.sshErrUnknown
    }
  }

  const sshTest = async () => {
    if (!canUseSsh) {
      notify({ kind: 'warning', title: g.incompleteTitle, message: g.sshIncompleteHost })
      return
    }
    setSshTestStatus('testing')
    setSshTestMessage(null)
    try {
      const result = await window.hermesDesktop.testConnectionConfig(sshPayload())
      if (result.reachable) {
        const message = g.sshReachable(result.host ?? state.sshHost, result.remotePlatform ?? '?')
        setSshTestStatus('ok')
        setSshTestMessage(message)
        notify({ kind: 'success', title: g.reachableTitle, message })
      } else {
        const message = sshErrorMessage(result.sshError, result.error)
        setSshTestStatus('error')
        setSshTestMessage(message)
        notify({ kind: 'warning', title: g.testFailed, message })
      }
    } catch (err) {
      setSshTestStatus('error')
      setSshTestMessage(err instanceof Error ? err.message : String(err))
      notifyError(err, g.testFailed)
    }
  }

  // Resolve the entered host via `ssh -G` and fill in any blank user/port the
  // alias expands to (so the saved config matches what ssh will actually use).
  const sshResolve = async () => {
    const host = state.sshHost.trim()
    if (!host || !window.hermesDesktop?.sshResolveHost) return
    try {
      const resolved = await window.hermesDesktop.sshResolveHost(host)
      setState(current => ({
        ...current,
        sshUser: current.sshUser.trim() || resolved.user || '',
        sshPort: current.sshPort ?? (resolved.port && resolved.port !== 22 ? resolved.port : null),
        sshKeyPath: current.sshKeyPath.trim() || resolved.identityFile || ''
      }))
    } catch {
      // best-effort enrichment; leave the fields as entered
    }
  }

  const sshSave = async (apply: boolean) => {
    if (!canUseSsh) {
      notify({ kind: 'warning', title: g.incompleteTitle, message: g.sshIncompleteHost })
      return
    }
    setSaving(true)
    try {
      const next = apply
        ? await window.hermesDesktop.applyConnectionConfig(sshPayload())
        : await window.hermesDesktop.saveConnectionConfig(sshPayload())
      setState(next)
      notify({
        kind: 'success',
        title: apply ? g.restartingTitle : g.savedTitle,
        message: apply ? g.restartingMessage : g.savedMessage
      })
    } catch (err) {
      notifyError(err, apply ? g.applyFailed : g.saveFailed)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <LoadingState label={g.loading} />
  }

  if (!window.hermesDesktop?.getConnectionConfig) {
    return (
      <EmptyState
        description={g.unavailableDesc}
        title={g.unavailableTitle}
      />
    )
  }

  return (
    <SettingsContent>
      <div className="mb-5">
        <div className="flex items-center gap-2 text-[length:var(--conversation-text-font-size)] font-medium">
          <Globe className="size-4 text-muted-foreground" />
          {g.title}
          {state.envOverride ? <Pill tone="primary">{g.envOverride}</Pill> : null}
        </div>
        <p className="mt-2 max-w-2xl text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)">
          {g.intro}
        </p>
      </div>

      {namedProfiles.length > 0 ? (
        <div className="mb-5 grid gap-2">
          <div className="text-[length:var(--conversation-caption-font-size)] font-medium text-(--ui-text-secondary)">
            {g.appliesTo}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <ScopeChip active={scope === null} label={g.allProfiles} onSelect={() => setScope(null)} />
            {namedProfiles.map(profile => (
              <ScopeChip
                active={scope === profile.name}
                key={profile.name}
                label={profile.name}
                onSelect={() => setScope(profile.name)}
              />
            ))}
          </div>
          <p className="text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)">
            {scope === null ? g.defaultConnection : g.profileConnection(scope)}
          </p>
        </div>
      ) : null}

      {state.envOverride ? (
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-[length:var(--conversation-caption-font-size)] text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <div>
            <div className="font-medium">{g.envOverrideTitle}</div>
            <div className="mt-1 leading-5">
              {g.envOverrideDesc}
            </div>
          </div>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <ModeCard
          active={state.mode === 'local'}
          description={g.localDesc}
          disabled={state.envOverride}
          icon={Monitor}
          onSelect={() => setState(current => ({ ...current, mode: 'local' }))}
          title={g.localTitle}
        />
        <ModeCard
          active={state.mode === 'remote'}
          description={g.remoteDesc}
          disabled={state.envOverride}
          icon={Globe}
          onSelect={() => setState(current => ({ ...current, mode: 'remote' }))}
          title={g.remoteTitle}
        />
        <ModeCard
          active={state.mode === 'ssh'}
          description={g.sshDesc}
          disabled={state.envOverride}
          icon={Network}
          onSelect={() => setState(current => ({ ...current, mode: 'ssh' }))}
          title={g.sshTitle}
        />
      </div>

      <div className="mt-5 grid gap-1">
        {state.mode === 'remote' ? (
          <ListRow
            action={
              <Input
                className={cn('h-8', CONTROL_TEXT)}
                disabled={state.envOverride}
                onChange={event => setState(current => ({ ...current, remoteUrl: event.target.value }))}
                placeholder="https://gateway.example.com/hermes"
                value={state.remoteUrl}
              />
            }
            description={g.remoteUrlDesc}
            title={g.remoteUrlTitle}
          />
        ) : null}

        {state.mode === 'remote' && probeStatus === 'probing' ? (
          <div className="flex items-center gap-2 py-3 text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)">
            <Loader2 className="size-4 animate-spin" />
            {g.probing}
          </div>
        ) : null}

        {state.mode === 'remote' && probeStatus === 'error' ? (
          <div className="flex items-start gap-2 py-3 text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            {g.probeError}
          </div>
        ) : null}

        {/* OAuth / password gateways: present a sign-in button + connection status. */}
        {state.mode === 'remote' && authResolved && authMode === 'oauth' ? (
          <ListRow
            action={
              oauthConnected ? (
                <div className="flex items-center gap-2">
                  <Pill tone="primary">
                    <Check className="size-3" /> {g.signedIn}
                  </Pill>
                  <Button disabled={signingIn || state.envOverride} onClick={() => void signOut()} variant="outline">
                    {signingIn ? <Loader2 className="animate-spin" /> : null}
                    {g.signOut}
                  </Button>
                </div>
              ) : (
                <Button disabled={signingIn || state.envOverride || !trimmedUrl} onClick={() => void signIn()}>
                  {signingIn ? <Loader2 className="animate-spin" /> : <LogIn />}
                  {isPasswordProvider ? g.signIn : g.signInWith(providerLabel)}
                </Button>
              )
            }
            description={
              oauthConnected
                ? isPasswordProvider
                  ? g.authSignedInPassword
                  : g.authSignedInOauth
                : isPasswordProvider
                  ? g.authNeedsPassword
                  : g.authNeedsOauth(providerLabel)
            }
            title={g.authTitle}
          />
        ) : null}

        {/* Session-token gateways: keep the existing token entry box. */}
        {state.mode === 'remote' && authResolved && authMode === 'token' ? (
          <ListRow
            action={
              <Input
                autoComplete="off"
                className={cn('h-8 font-mono', CONTROL_TEXT)}
                disabled={state.envOverride}
                onChange={event => setRemoteToken(event.target.value)}
                placeholder={
                  state.remoteTokenSet ? g.existingToken(state.remoteTokenPreview ?? g.savedToken) : g.pasteSessionToken
                }
                type="password"
                value={remoteToken}
              />
            }
            description={g.tokenDesc}
            title={g.tokenTitle}
          />
        ) : null}

        {/* SSH mode: connect via the box's SSH access; no token to copy. */}
        {state.mode === 'ssh' ? (
          <>
            <ListRow
              action={
                <Input
                  className={cn('h-8', CONTROL_TEXT)}
                  disabled={state.envOverride}
                  list="hermes-ssh-host-suggestions"
                  onBlur={() => void sshResolve()}
                  onChange={event => setState(current => ({ ...current, sshHost: event.target.value }))}
                  placeholder="user@mac-mini.local  or  mac-mini"
                  value={state.sshHost}
                />
              }
              description={g.sshHostDesc}
              title={g.sshHostTitle}
            />
            {sshHostSuggestions.length > 0 ? (
              <datalist id="hermes-ssh-host-suggestions">
                {sshHostSuggestions.map(host => (
                  <option key={host} value={host} />
                ))}
              </datalist>
            ) : null}
            <ListRow
              action={
                <Input
                  className={cn('h-8', CONTROL_TEXT)}
                  disabled={state.envOverride}
                  onChange={event => setState(current => ({ ...current, sshUser: event.target.value }))}
                  placeholder={g.sshUserPlaceholder}
                  value={state.sshUser}
                />
              }
              description={g.sshUserDesc}
              title={g.sshUserTitle}
            />
            <ListRow
              action={
                <Input
                  className={cn('h-8', CONTROL_TEXT)}
                  disabled={state.envOverride}
                  onChange={event =>
                    setState(current => ({
                      ...current,
                      sshPort: event.target.value.trim() ? Number.parseInt(event.target.value, 10) || null : null
                    }))
                  }
                  placeholder="22"
                  value={state.sshPort != null ? String(state.sshPort) : ''}
                />
              }
              description={g.sshPortDesc}
              title={g.sshPortTitle}
            />
            <ListRow
              action={
                <Input
                  className={cn('h-8', CONTROL_TEXT)}
                  disabled={state.envOverride}
                  onChange={event => setState(current => ({ ...current, sshKeyPath: event.target.value }))}
                  placeholder="~/.ssh/id_ed25519"
                  value={state.sshKeyPath}
                />
              }
              description={g.sshKeyDesc}
              title={g.sshKeyTitle}
            />
            <ListRow
              action={
                <Input
                  className={cn('h-8', CONTROL_TEXT)}
                  disabled={state.envOverride}
                  onChange={event => setState(current => ({ ...current, sshRemoteHermesPath: event.target.value }))}
                  placeholder={g.sshHermesPathPlaceholder}
                  value={state.sshRemoteHermesPath}
                />
              }
              description={g.sshHermesPathDesc}
              title={g.sshHermesPathTitle}
            />
            {sshTestStatus !== 'idle' && sshTestMessage ? (
              <div
                className={cn(
                  'flex items-start gap-2 py-3 text-[length:var(--conversation-caption-font-size)]',
                  sshTestStatus === 'ok' ? 'text-primary' : 'text-(--ui-text-tertiary)'
                )}
              >
                {sshTestStatus === 'testing' ? (
                  <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin" />
                ) : sshTestStatus === 'ok' ? (
                  <Check className="mt-0.5 size-4 shrink-0" />
                ) : (
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                )}
                <span>{sshTestMessage}</span>
              </div>
            ) : null}
          </>
        ) : null}
      </div>

      {lastTest ? <div className="mt-4 text-xs text-primary">{lastTest}</div> : null}

      <div className="mt-6 flex flex-wrap items-center justify-end gap-4">
        {state.mode === 'ssh' ? (
          <>
            <Button
              className="mr-auto"
              disabled={state.envOverride || sshTestStatus === 'testing' || !canUseSsh}
              onClick={() => void sshTest()}
              size="sm"
              variant="text"
            >
              {sshTestStatus === 'testing' ? <Loader2 className="animate-spin" /> : null}
              {g.sshTestConnection}
            </Button>
            <Button
              disabled={state.envOverride || saving}
              onClick={() => void sshSave(false)}
              size="sm"
              variant="textStrong"
            >
              {g.saveForRestart}
            </Button>
            <Button disabled={state.envOverride || saving || !canUseSsh} onClick={() => void sshSave(true)} size="sm">
              {saving ? <Loader2 className="animate-spin" /> : null}
              {g.sshConnect}
            </Button>
          </>
        ) : (
          <>
            <Button
              className="mr-auto"
              disabled={state.envOverride || testing || !canUseRemote}
              onClick={() => void testRemote()}
              size="sm"
              variant="text"
            >
              {testing ? <Loader2 className="animate-spin" /> : null}
              {g.testRemote}
            </Button>
            <Button disabled={state.envOverride || saving} onClick={() => void save(false)} size="sm" variant="textStrong">
              {g.saveForRestart}
            </Button>
            <Button disabled={state.envOverride || saving} onClick={() => void save(true)} size="sm">
              {saving ? <Loader2 className="animate-spin" /> : null}
              {g.saveAndReconnect}
            </Button>
          </>
        )}
      </div>

      <div className="mt-6 grid gap-1">
        <ListRow
          action={
            <Button onClick={() => void window.hermesDesktop?.revealLogs()} size="sm" variant="textStrong">
              <FileText />
              {g.openLogs}
            </Button>
          }
          description={g.diagnosticsDesc}
          title={g.diagnostics}
        />
      </div>
    </SettingsContent>
  )
}
