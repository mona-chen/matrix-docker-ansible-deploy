# TMCP PROTO.md Issues and Clarifications

This document tracks issues, inconsistencies, and clarifications needed in PROTO.md regarding the TMCP Application Service implementation.

---

## Issue #1: sender_localpart Confusion

### Location in PROTO.md
- Line 223: `sender_localpart: _tmcp`
- Line 1818: `sender_localpart: _tmcp_payments`

### Problem
PROTO.md shows **different sender_localpart values** in different sections without explaining the relationship between them:

**Section 3.1.2 (Line 223):**
```yaml
sender_localpart: _tmcp
# This creates: @_tmcp:tween.im
```

**Section 4.11.2 (Line 1818):**
```yaml
sender_localpart: _tmcp_payments
# This would create: @_tmcp_payments:tween.im
```

### Actual Behavior

An Application Service can have **only ONE** `sender_localpart` per registration. This creates exactly one main bot user.

**Correct Understanding:**
- `sender_localpart: _tmcp` → Creates `@_tmcp:tween.im` (main TMCP bot)
- Payment bot `@_tmcp_payments:tween.im` is created via **namespace**, not sender_localpart
- `@_tmcp_payments` exists in the namespace `@_tmcp_[a-zA-Z0-9.-]+:tween\.im`

### Evidence from Real Bridges

**WhatsApp Bridge:**
```yaml
sender_localpart: _bot_whatsappbot
# Creates: @_bot_whatsappbot:tween.im

namespaces:
  users:
    - regex: '^@whatsapp_.*:tween\.im$'     # Puppet users
        exclusive: true
    - regex: '^@whatsappbot:tween\.im$'        # Main bot
        exclusive: true
```

**Discord Bridge:**
```yaml
sender_localpart: _discord_bot
# Creates: @_discord_bot:tween.im

namespaces:
  users:
    - regex: '@_discord_.*:tween\.im'
        exclusive: true
```

### Clarification Needed

**PROTO.md Section 4.11.2 should clarify:**

> The TMCP Application Service has a single `sender_localpart: _tmcp` which creates the main bot user `@_tmcp:tween.im`.
>
> The virtual payment bot `@_tmcp_payments:tween.im` is managed via the namespace pattern `@_tmcp_[a-zA-Z0-9.-]+:tween\.im` and is created automatically by the homeserver when first used, NOT via sender_localpart.

---

## Issue #2: Namespace Pattern Inconsistency

### Location in PROTO.md
- Line 1819: Shows `@_tmcp_payments:<hs>` as the required pattern
- Line 1825: Shows exact user ID `@_tmcp_payments:tween.example`

### Problem

PROTO.md shows `<hs>` placeholder notation which is unclear:
- Is `:tween.example` the same as `<hs>`?
- Does `<hs>` mean "homeserver domain"?
- What's the exact regex pattern?

### Actual Implementation

In Matrix AS registration files, you use actual domain names:

```yaml
# NOT: regex: "@_tmcp_payments:<hs>"  ❌
# BUT: regex: "@_tmcp_payments:tween\.im"  ✅
```

### Clarification Needed

**PROTO.md should show actual YAML examples:**

```yaml
namespaces:
  users:
      - exclusive: true
        regex: "@_tmcp_payments:tween\.im"
      - exclusive: true
        regex: "@_tmcp:tween\.im"
      - exclusive: true
        regex: "@_tmcp_[a-zA-Z0-9.-]+:tween\.im"
```

---

## Issue #3: Bot User Creation Process

### Location in PROTO.md
- Section 4.11.2: "TMCP Server registers a virtual payment bot user"

### Problem

PROTO.md implies that TMCP Server "registers" bot users, but in Matrix:
- Bot users are created by Synapse when loading registration
- Namespaces define which user IDs the AS controls
- Bot users exist "virtually" - created on first use (invite, mention, etc.)

### How It Actually Works

**When Synapse Loads Registration:**
1. Reads `tmcp-registration.yaml`
2. Parses `sender_localpart: _tmcp`
3. Creates main bot user: `@_tmcp:tween.im`
4. Parses namespace regexes
5. Sets up namespace exclusivity rules

**When Bot User is First Invited:**
1. User invites `@_tmcp_payments:tween.im` to a room
2. Synapse checks if user ID matches AS namespace
3. If yes, Synapse automatically creates the user
4. Sends join event to TMCP AS

### Evidence from WhatsApp Bridge

The WhatsApp bridge demonstrates this perfectly:

```yaml
# WhatsApp creates TWO separate namespace patterns:
# 1. For puppet users (dynamic, per WhatsApp contact)
namespaces:
  users:
      - regex: '^@whatsapp_.*:tween\.im$'
        exclusive: true
        # Matches: @whatsapp_user123, @whatsapp_jane, etc.

      - regex: '^@whatsappbot:tween\.im$'
        exclusive: true
        # Matches: @whatsappbot (main bot, NOT from sender_localpart!)

sender_localpart: _bot_whatsappbot
# Creates: @_bot_whatsappbot:tween.im (different from @whatsappbot!)
```

**Key Observations:**

1. **Main bot from sender_localpart**: `@_bot_whatsappbot:tween.im`
2. **Main bot from dedicated namespace**: `@whatsappbot:tween.im`
3. **These are TWO DIFFERENT users!**
4. **Puppet users**: Created on-demand when WhatsApp contacts are bridged

### WhatsApp Bot User Architecture

```
@whatsappbot:tween.im
  └─> Created via namespace regex: '^@whatsappbot:tween\.im$'
  └─> Used as the "WhatsApp Bot" user users interact with
  └─> Has display name: "WhatsApp Bot"
  └─> Has avatar: WhatsApp logo
  └─> Can be invited to any room

@_bot_whatsappbot:tween.im
  └─> Created via sender_localpart: _bot_whatsappbot
  └─> Used internally by the bridge
  └─> NOT meant for direct user interaction
  └─> May have restricted permissions or different role

@whatsapp_jane:tween.im
  └─> Created via namespace regex: '^@whatsapp_.*:tween\.im$'
  └─> Puppet user for WhatsApp contact "Jane"
  └─> Created automatically when Jane is added to Matrix bridge
  └─> Messages from Jane appear as from this user ID
```

### Why WhatsApp Has Two Main Bot Patterns

**Reason: Separation of concerns**

1. **`@whatsappbot:tween.im`** - User-facing bot
   - Users can invite this bot to rooms
   - Shows up in user directory as "WhatsApp Bot"
   - Administered manually by bridge admin
   - Can be configured with nice display name and avatar

2. **`@_bot_whatsappbot:tween.im`** - Internal AS identity
   - Used by bridge when acting as AS (sending events)
   - May have admin-level permissions
   - Not meant for users to interact with directly

**This is a WhatsApp-specific pattern**, NOT a Matrix requirement!

### TMCP's Correct Approach

**Based on Discord bridge (the cleanest example):**

```yaml
# TMCP should use single namespace pattern approach:

sender_localpart: _tmcp
# Creates: @_tmcp:tween.im (main bot)

namespaces:
  users:
      - regex: '@_tmcp:tween\.im'              # Main bot
        exclusive: true
      - regex: '@_tmcp_[a-zA-Z0-9.-]+:tween\.im'  # Other TMCP bots
        exclusive: true
```

**User Bot Users:**
- `@_tmcp:tween.im` - Main TMCP bot (from sender_localpart)
- `@_tmcp_payments:tween.im` - Payment notifications
- `@_tmcp_updater:tween.im` - Mini-app update notifications

**All covered by namespace patterns**, no need for separate sender_localpart user like WhatsApp's `@_bot_whatsappbot`.

### Clarification Needed

**PROTO.md should explain:**

> "Unlike some bridges (e.g., WhatsApp) that maintain separate internal bot users via sender_localpart, TMCP uses the Discord bridge pattern where a single namespace pattern `@_tmcp.*:tween\.im` covers both the main bot (from sender_localpart) and all other TMCP-controlled bot users."

---

## Issue #4: sender_localpart Purpose

### Location in PROTO.md
- Multiple sections mention sender_localpart without explaining its purpose

### Problem

PROTO.md doesn't clearly explain what `sender_localpart` does:

From Matrix AS API:
> "The localpart of user associated with the application service. Events will be sent to AS if this user is target of event, or is a joined member of room where event occurred."

### Actual Behavior

**sender_localpart creates a Matrix user that:**

1. **Receives events**: When targeted or mentioned
2. **Joins rooms**: When AS needs to participate
3. **Can send events**: Via Identity Assertion (using as_token)

**Example:**

```yaml
sender_localpart: _tmcp
# Creates: @_tmcp:tween.im

# When:
# - User @_tmcp:tween.im is invited to a room → AS receives room events
# - Someone mentions @_tmcp:tween.im → AS receives mention
# - AS needs to send an event → AS acts as @_tmcp:tween.im
```

### Clarification Needed

**PROTO.md Section 3.1.2 should add:**

> The `sender_localpart` parameter creates a Matrix user ID that serves as the Application Service's primary identity.
>
> This user:
> - Automatically receives events when targeted or mentioned
> - Can be invited to rooms to observe all room events
> - Can be used by the AS to send events via the Client-Server API (using Identity Assertion)
>
> All other bot users (e.g., `@_tmcp_payments:tween.im`) must be covered by namespace regexes, but are NOT created via sender_localpart.

---

## Issue #5: Namespace vs sender_localpart Coverage

### Location in PROTO.md
- Section 4.11.2: Implies `@_tmcp_payments` is created via sender_localpart

### Problem

PROTO.md incorrectly suggests that `@_tmcp_payments` is created via `sender_localpart: _tmcp_payments`, but:

1. **Only ONE sender_localpart is allowed per AS registration**
2. **TMCP's actual sender_localpart is `_tmcp`** (from Section 3.1.2)
3. **`@_tmcp_payments` is created via namespace, not sender_localpart**

### Correct Understanding

```yaml
# TMCP Registration:

sender_localpart: _tmcp
# Creates: @_tmcp:tween.im (PRIMARY bot user)

namespaces:
  users:
      - regex: '@_tmcp:tween\.im'               # Covers sender_localpart user
      - regex: '@_tmcp_payments:tween\.im'     # Payment bot (namespace)
      - regex: '@_tmcp_updater:tween\.im'       # Updater bot (namespace)
      - regex: '@_tmcp_[a-zA-Z0-9.-]+:tween\.im'  # Other TMCP bots
        exclusive: true
```

**Coverage:**
- `@_tmcp:tween.im` - From sender_localpart, covered by `@_tmcp:tween\.im`
- `@_tmcp_payments:tween.im` - From namespace, covered by `@_tmcp_[a-zA-Z0-9.-]+:tween\.im`
- `@_tmcp_updater:tween.im` - From namespace, covered by `@_tmcp_[a-zA-Z0-9.-]+:tween\.im`

### Clarification Needed

**PROTO.md Section 4.11.2 should be corrected:**

> **Incorrect (current PROTO.md):**
> "TMCP Server registers a virtual payment bot user... sender_localpart: _tmcp_payments"
>
> **Correct:**
> "TMCP Server defines the virtual payment bot user via namespace regex. The main AS user is created from `sender_localpart: _tmcp`, which results in `@_tmcp:tween.im`. The payment bot `@_tmcp_payments:tween.im` is automatically created by the homeserver when first invited to a room, as it falls within the namespace `@_tmcp_[a-zA-Z0-9.-]+:tween\.im`."

---

## Issue #6: Alias Namespaces Missing Examples

### Location in PROTO.md
- Line 1824: Shows `@_tmcp_payments:<hs>` but doesn't show alias namespace

### Problem

PROTO.md defines user namespaces but doesn't show complete example with alias namespaces.

### What Should Be Added

```yaml
namespaces:
  users:
      - exclusive: true
        regex: "@_tmcp:tween\.im"
      - exclusive: true
        regex: "@_tmcp_payments:tween\.im"
      - exclusive: true
        regex: "@ma_[a-zA-Z0-9_]+:tween\.im"
  aliases:
      - exclusive: true
        regex: "#_ma_[a-zA-Z0-9_]+:[a-zA-Z0-9.-]+:tween\.im"
```

### Example Usage

```yaml
# Mini-app "Shop" creates a room alias:
# Room Alias: #_ma_shop_001:product-updates:tween.im
#
# This alias:
# - Is managed by: @_ma_shop_001:tween.im (bot user)
# - Can only be created by TMCP AS (exclusive namespace)
# - Users can join via this alias
# - TMCP AS receives all events in this room
```

### Clarification Needed

**Add to PROTO.md Section 3.1.2:**

> "TMCP mini-apps can create and manage room aliases in the `#_ma_*` namespace. These aliases are exclusive, meaning only the TMCP AS can create or modify them. When a user joins a room via a `#_ma_*` alias, the TMCP AS receives all events for that room."

---

## Summary of Recommended Changes

### PROTO.md Edits Needed

1. **Section 3.1.2**: Clarify `sender_localpart` behavior and purpose
2. **Section 3.1.2**: Show actual YAML with real domain names (not `<hs>`)
3. **Section 4.11.2**: Remove incorrect `sender_localpart: _tmcp_payments` reference
4. **Section 4.11.2**: Explain that `@_tmcp_payments` is created via namespace
5. **Section 4.11.2**: Add alias namespace example
6. **Throughout**: Use consistent terminology (don't mix "registers" vs "creates via namespace")

### Additional Sections to Add

- **Bot User Creation Process**: Explain how Synapse creates users on first use
- **Namespace Coverage**: Explain that `sender_localpart` user must be covered by namespace
- **WhatsApp vs Discord Pattern Comparison**: Show why Discord pattern is cleaner

---

## References

- Matrix AS API v1.11: https://spec.matrix.org/v1.11/application-service-api/
- Discord bridge configuration: `roles/custom/matrix-bridge-appservice-discord/defaults/main.yml`
- WhatsApp bridge configuration: `roles/custom/matrix-bridge-mautrix-whatsapp/defaults/main.yml`
- Signal bridge configuration: `roles/custom/matrix-bridge-mautrix-signal/defaults/main.yml`
- TMCP PROTO.md: `PROTO.md`
