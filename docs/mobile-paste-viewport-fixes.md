# Mobile Paste & Viewport Fixes

## Issues Fixed

### Issue 1: Paste Not Working
**Problem:** Cannot paste text on mobile devices

**Root Causes:**
1. Touch-action constraints were too restrictive
2. No explicit paste event handling for mobile
3. Potential focus/blur conflicts interfering with paste menu

**Solutions:**
1. Removed touch-action from main terminal container
2. Set `touch-action: auto` on xterm-helper-textarea specifically
3. Added explicit paste event handlers at container level
4. Removed aggressive blur-prevention that might block paste menu
5. Manual websocket send when paste detected

### Issue 2: Input Field Not Visible Until Typing
**Problem:** When clicking on terminal, input area not visible; only centers after typing starts

**Root Causes:**
1. Fixed header on mobile created padding offset
2. Keyboard opening didn't scroll terminal into view
3. Aggressive scrollIntoView on every tap caused jankiness
4. Padding persisted even when keyboard open and header hidden

**Solutions:**
1. Only scroll into view when keyboard actually appears (visualViewport resize)
2. Use 'instant' scroll behavior to avoid animation conflicts
3. Remove padding when keyboard open (`body.keyboard-open .terminal-container`)
4. Scroll to 'start' position (top of viewport) not 'center'

## Code Changes

### CSS Changes

```css
/* Before - restrictive touch-action on everything */
@media (max-width: 768px) {
    #terminal { touch-action: manipulation; }
    #terminal .xterm-viewport { touch-action: pan-y !important; }
    #terminal .xterm-screen { touch-action: manipulation !important; }
}

/* After - only restrict viewport scrolling, allow all touch on textarea */
@media (max-width: 768px) {
    #terminal .xterm-viewport { touch-action: pan-y !important; }
    #terminal .xterm-helper-textarea { touch-action: auto !important; }
}
```

```css
/* Added: Remove padding when keyboard open */
body.keyboard-open .terminal-container {
    padding-top: 0;
}
```

### JavaScript Changes

**Removed aggressive focus/blur management:**
```javascript
// REMOVED: Blur prevention that blocked paste menu
state.terminal.textarea.addEventListener('blur', (e) => {
    setTimeout(() => { state.terminal.focus(); }, 200);
});

// REMOVED: Aggressive scrollIntoView on every tap
state.terminal.textarea.scrollIntoView({ behavior: 'smooth' });
```

**Added smart scrollIntoView only when keyboard appears:**
```javascript
window.visualViewport.addEventListener('resize', () => {
    if (window.visualViewport.height < window.innerHeight * 0.75) {
        requestAnimationFrame(() => {
            textarea.scrollIntoView({
                behavior: 'instant',  // No animation
                block: 'start',       // Top of viewport
                inline: 'nearest'
            });
        });
    }
});
```

**Added explicit paste handling:**
```javascript
// Catch paste events at container level
container.addEventListener('paste', async (e) => {
    if (state.websocket?.readyState === WebSocket.OPEN) {
        e.preventDefault();
        const text = e.clipboardData?.getData('text/plain');
        if (text) {
            state.websocket.send(text);
        }
    }
});
```

## Testing Checklist

- [ ] **Paste functionality:**
  - [ ] Long-press → Paste menu appears
  - [ ] Tap "Paste" → text appears in terminal
  - [ ] Clipboard button above keyboard works
  - [ ] Console shows "Paste event detected" message

- [ ] **Input visibility:**
  - [ ] Tap terminal → keyboard appears
  - [ ] Terminal scrolls into view immediately
  - [ ] No blank space or "hidden" input area
  - [ ] Can see cursor and typing position
  - [ ] No animation jank or stuttering

- [ ] **Header behavior:**
  - [ ] Header visible when keyboard closed
  - [ ] Header slides away when keyboard opens
  - [ ] Extra space (70px padding) removed when keyboard open
  - [ ] Header returns smoothly when keyboard dismissed

## Debug Mode

To see paste events in console:
1. Open browser devtools on mobile (Safari Web Inspector or Chrome Remote Debugging)
2. Look for console messages:
   - "Paste event detected on mobile"
   - "Paste event on container"
   - "Sending pasted text: [first 50 chars]"

## Browser Compatibility

### Paste API Support
- iOS Safari 13.4+: ✅ Clipboard API
- Chrome Android: ✅ Full support
- Firefox Android: ✅ Partial support

### visualViewport API
- iOS Safari 13+: ✅
- Chrome Android: ✅
- All modern mobile browsers: ✅

## Rollback

If paste still doesn't work, the issue might be:
1. Browser permissions (some browsers require HTTPS for clipboard)
2. WebSocket not connected
3. xterm.js configuration issue

To revert all mobile changes:
```bash
git diff web/index.html  # Review changes
git checkout HEAD~1 web/index.html  # Revert
```

## Next Steps

If paste still fails:
1. Check browser console for errors
2. Verify WebSocket connection is open
3. Test on different mobile browsers (Safari vs Chrome)
4. Check if site needs to be served over HTTPS
5. Try programmatic clipboard API as fallback
