## Summary

Pass the owning profile through desktop secondary session windows so opening a stored session in a new window resumes it against the correct profile context.

Previously, `openSessionInNewWindow()` only forwarded `sessionId` and `watch`, while the secondary-window URL and route-resume path had no profile hint. That meant a pop-out window could fall back to the active/default profile during cold resume, which is wrong for profile-scoped sessions.

## Changes

- Forward `profile` from session-row and session-actions-menu into the desktop bridge.
- Include `profile=` in the secondary-window URL before the hash route.
- Read the profile hint in the renderer and pass it into routed resume.
- Prefer the hinted profile during session lookup and gateway swap.
- Key the secondary-window registry by profile + session id so same-id sessions from different profiles cannot collide.
- Add regressions for URL construction, bridge forwarding, and routed resume hinting.

## Tests

```text
node --test apps/desktop/electron/session-windows.test.cjs
npm run test:ui -- src/store/windows.test.ts src/app/session/hooks/use-route-resume.test.tsx
npm run typecheck
```

