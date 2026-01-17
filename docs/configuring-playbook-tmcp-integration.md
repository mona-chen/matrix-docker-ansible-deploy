# TMCP Integration Guide

This guide explains how the TMCP Application Service integrates with Matrix Synapse and how to configure it correctly.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Application Service Registration](#application-service-registration)
3. [Bot Users](#bot-users)
4. [Room Participation](#room-participation)
5. [Namespace Configuration](#namespace-configuration)
6. [Event Handling](#event-handling)
7. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

TMCP (Tween Mini-App Communication Protocol) operates as a Matrix Application Service (AS). This allows it to:

- **Observe Matrix events** - Receive events from rooms where TMCP bot users participate
- **Inject Matrix events** - Send payment notifications, mini-app events, etc. into rooms
- **Act as Matrix users** - Use AS-controlled user IDs to interact with rooms

### Key Components

```
┌─────────────────────────────────────────────────────────────┐
│                   TMCP Architecture                      │
├─────────────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────┐    ┌─────────────────┐   │
│  │ TMCP Server   │    │ Matrix Synapse │   │
│  │ (External)    │────▶│ (core.tween.im) │   │
│  └──────────────┘    └─────────────────┘   │
│        ▲                       │              │
│        │                       ▼              │
│  ┌──────────────────────────────────┐            │
│  │ Application Service           │            │
│  │ (matrix-tmcp-integration)    │            │
│  │ Registration:                 │            │
│  │ - Namespaces configured        │            │
│  │ - Bot users created          │            │
│  └──────────────────────────────────┘            │
│                                                      │
└─────────────────────────────────────────────────────────────┘
```

### How It Works

1. **Registration**: Synapse loads `tmcp-registration.yaml` and configures AS namespaces
2. **Bot Creation**: Synapse automatically creates bot users for `sender_localpart` and namespace patterns
3. **Event Flow**:
   - User invites bot to room → Homeserver notifies TMCP AS → AS processes event
   - TMCP AS injects event → Uses `as_token` as `access_token` to call Client-Server API

---

## Application Service Registration

### Registration File Location

**File**: `/data/tmcp-registration.yaml` (inside Synapse container)
**Created by**: `roles/custom/matrix-tmcp-integration/tasks/main.yml`

### Registration Configuration

```yaml
id: tween-miniapps
url: https://tmcp.tween.im
as_token: "{{ matrix_synapse_tmcp_appservice_token }}"  # AS authenticates to HS
hs_token: "{{ matrix_synapse_tmcp_homeserver_token }}"  # HS authenticates to AS
sender_localpart: _tmcp
rate_limited: false
namespaces:
  users:
    - exclusive: true
      regex: "@_tmcp_payments:tween\.im"           # Payment bot
    - exclusive: true
      regex: "@_tmcp:[a-zA-Z0-9.-]+\.im"     # TMCP system bots
    - exclusive: true
      regex: "@ma_[a-zA-Z0-9_]+:[a-zA-Z0-9.-]+\.im"  # Mini-app bots
    - exclusive: true
      regex: "@_tmcp_updater:tween\.im"           # Mini-app updater bot
  aliases:
    - exclusive: true
      regex: "#_ma_[a-zA-Z0-9_]+:[a-zA-Z0-9.-]+\.im"  # Mini-app room aliases
  protocols:
    - tween
```

### Tokens Configuration

Located in `inventory/host_vars/core.tween.im/vars.yml`:

```yaml
# AS Tokens (hardcoded for security)
matrix_synapse_tmcp_appservice_token: "54280d605e23adf6bd5d66ee07a09196dbab0bd87d35f8ecc1fd70669f709502"
matrix_synapse_tmcp_homeserver_token: "874542cda496ffd03f8fd283ad37d8837572aad0734e92225c5f7fffd8c91bd1"
```

### MAS Client Registration

```yaml
# OAuth 2.0 client for TMCP Server
matrix_authentication_service_config_clients_custom:
  - client_id: 01H9KJ7NV0HG7CJ1ZX4KCT3CE6
    client_auth_method: client_secret_post
    client_secret: 'pF/Y9eiJXTHASLFNPOIzXiym0E9o1J7o5+UsHONumS0='
    grant_types:
      - urn:ietf:params:oauth:grant-type:token-exchange
      - refresh_token
      - authorization_code
      - client_credentials
    scope:
      - openid
      - urn:matrix:client:api:*
    redirect_uris:
      - https://tmcp.tween.im/api/v1/oauth/callback
```

---

## Bot Users

### User Creation in Matrix

Application Services create bot users through **registration, not direct creation**. When Synapse loads the registration file:

1. **`@_tmcp:tween.im`** - Main TMCP bot user
   - Created automatically from `sender_localpart: _tmcp`
   - Used as the primary identity for TMCP Server operations
   - Display name should be: "TMCP Bot" or "Tween Mini-App Bot"

2. **`@_tmcp_payments:tween.im`** - Payment notification bot
   - Namespace pattern: `@_tmcp_payments:tween\.im`
   - Purpose: Send payment receipts and status updates
   - Display name: "Tween Payments"
   - Avatar: Payment-themed icon

3. **`@_tmcp_updater:tween.im`** - Mini-app update bot
   - Namespace pattern: `@_tmcp_updater:tween\.im`
   - Purpose: Send mini-app update notifications
   - Display name: "Tween Mini-App Updater"

4. **`@ma_[id]:tween.im`** - Mini-app specific bots (dynamic)
   - Namespace pattern: `@ma_[a-zA-Z0-9_]+:[a-zA-Z0-9.-]+\.im`
   - Created dynamically by TMCP Server when mini-apps need bot users
   - Example: `@ma_shop_001:tween.im` for a shopping mini-app
   - Each mini-app can have its own bot user for notifications

### Bot User Characteristics

| Property | Value | Description |
|----------|---------|-------------|
| **Control** | Application Service | Controlled via AS registration, not regular users |
| **Password** | None | AS users don't have passwords (use `as_token`) |
| **Creation** | Automatic | Created by Synapse when registration is loaded |
| **Join** | Via Invitation | Must be invited by regular users or other AS users |
| **Permissions** | Full Namespace Control | Full control over users in exclusive namespace |

### How Bot Users Join Rooms

**Critical**: Application Services **CANNOT actively join rooms**. They are passive observers.

#### The Invitation Flow

```
Regular User (@alice:tween.im)
      │
      │ 1. Sends invite to @_tmcp_payments:tween.im
      │    PUT /_matrix/client/v3/rooms/!roomId/invite
      │    {"user_id": "@_tmcp_payments:tween.im"}
      │
      ▼
┌─────────────────────────────────────────────┐
│ Matrix Homeserver (core.tween.im)       │
│                                       │
│  2. Receives invite request          │
│  3. Checks namespace exclusivity     │
│  4. Verifies @_tmcp_payments is AS user │
│  5. Sends membership event to TMCP AS  │
│  6. Creates/joins bot user to room      │
└─────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│ TMCP AS (tmcp.tween.im)            │
│                                       │
│  7. Receives m.room.member (join)     │
│  8. Processes join event               │
│  9. Can now inject events into room  │
└─────────────────────────────────────────────┘
```

#### Event Flow for Room Join

When a regular user invites a TMCP bot:

1. **Client sends**: `PUT /_matrix/client/v3/rooms/!roomId/invite`
2. **Homeserver validates**:
   - User has permission to invite
   - Target user (`@_tmcp_payments:*`) is in AS-controlled namespace
3. **Homeserver creates bot user**: If `@_tmcp_payments:tween.im` doesn't exist
4. **Homeserver sends event to TMCP AS**:
   ```
   PUT /_matrix/app/v1/transactions/{txnId}
   Authorization: Bearer {{ hs_token }}
   {
     "events": [{
       "type": "m.room.member",
       "sender": "@alice:tween.im",
       "room_id": "!roomId:tween.im",
       "content": {
         "membership": "join",
         "displayname": "Tween Payments",
         "avatar_url": "mxc://..."
       },
       "event_id": "$..."
     }]
   }
   ```
5. **TMCP AS responds**: `200 OK`
6. **Bot is now in room** and can inject events

### Why AS Users Can't "Join" Themselves

From Matrix AS API v1.11 specification:

> "Application services are passive and can only observe events from homeserver. They can inject events into rooms they are participating in."

**Implications:**
- No `/join` endpoint for AS users (that's for client-server API)
- No password to authenticate
- Must wait for regular users or other AS users to invite them
- Once invited and joined, they receive all room events and can inject events

---

## Room Participation

### How TMCP Bot Users Participate in Rooms

Once a TMCP bot user has been invited and joined a room, it can:

1. **Receive all room events** - Every event in the room is sent to TMCP AS
2. **Send events to room** - Use Client-Server API with `as_token` as `access_token`

### Sending Events to Rooms

When TMCP Server needs to inject an event (e.g., payment notification):

```http
PUT /_matrix/client/v3/rooms/!roomId:tween.im/send/m.tween.payment.completed
Authorization: Bearer {{ matrix_synapse_tmcp_appservice_token }}
Content-Type: application/json

{
  "msgtype": "m.tween.payment",
  "payment_type": "completed",
  "txn_id": "txn_abc123",
  "amount": 5000.00,
  "currency": "USD",
  "sender": {
    "user_id": "@alice:tween.im",
    "display_name": "Alice"
  },
  "recipient": {
    "user_id": "@bob:tween.im",
    "display_name": "Bob"
  },
  "timestamp": "2025-01-17T14:30:00Z"
}
```

### Room Aliases

TMCP mini-apps can create room aliases in their namespace:

```yaml
# This alias would be: #_ma_shop_001:my-shop:tween.im
# Managed by: @_ma_shop_001:tween.im
```

**Usage**:
- Users can join `#_ma_shop_001:my-shop:tween.im`
- Room is effectively "managed" by that mini-app
- TMCP AS receives all events for that room

---

## Namespace Configuration

### Namespace Purpose

Namespaces define which users and rooms an Application Service has exclusive control over.

**Types of Namespaces:**
- **Users** - Matrix user IDs (`@localpart:domain.com`)
- **Aliases** - Room aliases (`#roomname:domain.com`)
- **Rooms** - Room IDs (`!randomId:domain.com`)

### Exclusive vs Non-Exclusive

| Type | Exclusive | Non-Exclusive | Use Case |
|-------|------------|---------------|-----------|
| **Users** | Only AS can create users in this namespace | Anyone can create, AS observes | Puppets, mini-app bots |
| **Aliases** | Only AS can manage aliases in this namespace | Anyone can join, AS observes | Bridged channels |
| **Rooms** | Only AS can manage rooms in this namespace | Anyone can create, AS observes | AS-managed rooms |

### TMCP Namespaces

All TMCP namespaces are **exclusive**:

```yaml
# Payment Bot - Payment notifications
@_tmcp_payments:tween.im
  └─> Control: Exclusive
  └─> Purpose: Send payment receipts

# TMCP System Bots - General TMCP operations
@_tmcp:tween.im
  └─> Control: Exclusive
  └─> Purpose: Main bot user

@_tmcp:*:tween.im
  └─> Control: Exclusive
  └─> Purpose: System-level bots (future use)

# TMCP Updater - Mini-app update notifications
@_tmcp_updater:tween.im
  └─> Control: Exclusive
  └─> Purpose: Mini-app update notifications

# Mini-App Bots - Dynamic per-mini-app bots
@ma_shop_001:tween.im
  └─> Control: Exclusive
  └─> Purpose: Shopping mini-app bot

@ma_payflow_002:tween.im
  └─> Control: Exclusive
  └─> Purpose: Payment flow mini-app bot

# Mini-App Room Aliases
#_ma_shop_001:product:updates:tween.im
  └─> Control: Exclusive
  └─> Purpose: Shop update room
```

### Namespace Regex Explanation

```yaml
# User namespaces
regex: "@_tmcp_payments:tween\.im"
#      ↑              ↑
#      |              │
#      |  Matches: @_tmcp_payments:tween.im
#      |              │
#      |    Note: \. matches literal dot (not any character)
#      |    If you wanted "any character after tween", use: tween\.im$

# Room alias namespace
regex: "#_ma_[a-zA-Z0-9_]+:[a-zA-Z0-9.-]+\\.im"
#         ↑               ↑
#         |               │
#         |    Matches: #_ma_shop_001:my-shop:tween.im
#         |    Note: \\ is needed to escape the . before other character classes
```

### Common Namespace Mistakes

```yaml
# ❌ WRONG - Double escaped
regex: "@_tmcp_payments:tween\\.im"
#      ↑↑↑↑
#      |  │   │
#      |  │   └─> This matches: @_tmcp_paymentsXtween.im (with X character)
#      |        because \. matches ANY character in regex character class

# ✅ CORRECT - Single escaped
regex: "@_tmcp_payments:tween\.im"
#      ↑↑
#      |  │
#      |  └─> This matches: @_tmcp_payments:tween.im (literal dot)
```

---

## Event Handling

### Homeserver → TMCP AS Flow

Synapse pushes events to TMCP AS via the Application Service API.

#### Transaction Endpoint

```http
PUT /_matrix/app/v1/transactions/{txnId}
Authorization: Bearer {{ matrix_synapse_tmcp_homeserver_token }}
Content-Type: application/json

{
  "events": [
    {
      "type": "m.room.member",
      "sender": "@alice:tween.im",
      "state_key": "@_tmcp_payments:tween.im",
      "content": {
        "membership": "join",
        "displayname": "Tween Payments",
        "avatar_url": "mxc://tween.im/avatar_payments"
      },
      "event_id": "$...",
      "origin_server_ts": 1737149600000,
      "room_id": "!room123:tween.im"
    },
    {
      "type": "m.room.message",
      "sender": "@alice:tween.im",
      "content": {
        "msgtype": "m.text",
        "body": "Hello everyone!"
      },
      "event_id": "$...",
      "room_id": "!room123:tween.im"
    }
  ]
}
```

#### Authorization

TMCP Server must validate `hs_token` in `Authorization` header.

### TMCP AS → Client API Flow

When TMCP AS needs to send events (Identity Assertion):

```http
PUT /_matrix/client/v3/rooms/!room123:tween.im/send/m.tween.payment.completed
Authorization: Bearer {{ matrix_synapse_tmcp_appservice_token }}
Content-Type: application/json

{
  "msgtype": "m.tween.payment",
  "payment_type": "completed",
  "txn_id": "txn_abc123",
  "amount": 5000.00,
  "currency": "USD",
  "sender": {
    "user_id": "@alice:tween.im",
    "display_name": "Alice",
    "avatar_url": "mxc://tween.im/alice"
  },
  "recipient": {
    "user_id": "@bob:tween.im",
    "display_name": "Bob",
    "avatar_url": "mxc://tween.im/bob"
  },
  "timestamp": "2025-01-17T14:30:00Z"
}
```

### Event Types Used by TMCP

| Event Type | Purpose | Namespace |
|-------------|---------|------------|
| `m.room.member` | Track joins/leaves | Standard Matrix |
| `m.room.message` | Receive chat messages | Standard Matrix |
| `m.tween.payment.completed` | Payment receipt | TMCP custom |
| `m.tween.payment.failed` | Payment failure | TMCP custom |
| `m.tween.wallet.p2p` | P2P transfer | TMCP custom |
| `m.tween.gift` | Group gift | TMCP custom |
| `m.tween.miniapp.launch` | Mini-app launch | TMCP custom |
| `m.tween.miniapp.updated` | Mini-app update | TMCP custom |

---

## Troubleshooting

### Bot Not Joining Room

**Symptom**: You invite `@_tmcp_payments:tween.im` but it doesn't appear in the room.

**Check Steps**:

1. **Verify registration file is loaded**:
   ```bash
   docker exec -it matrix-synapse cat /data/tmcp-registration.yaml
   ```

2. **Check Synapse logs for namespace errors**:
   ```bash
   docker logs matrix-synapse 2>&1 | grep -i "tmcp\|namespace"
   ```

3. **Verify bot user exists**:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://core.tween.im/_matrix/client/v3/profile/@_tmcp_payments:tween.im
   ```

4. **Check if user is already in room**:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     "https://core.tween.im/_matrix/client/v3/rooms/!roomId/state/m.room.member/@_tmcp_payments:tween.im"
   ```

**Common Causes**:
- Namespace regex doesn't match user ID
- Registration file not reloaded after changes
- Bot user creation failed (check Synapse config)
- Invitation rejected (user doesn't have permission)

### Events Not Being Received by TMCP Server

**Symptom**: TMCP Server doesn't receive events from Synapse.

**Check Steps**:

1. **Verify `hs_token` is correct in registration**:
   ```yaml
   hs_token: "{{ matrix_synapse_tmcp_homeserver_token }}"
   ```

2. **Check TMCP AS logs for authorization failures**:
   ```bash
   # If TMCP AS is running in container
   docker logs tmcp-server 2>&1 | grep -i "authorization\|401\|403"
   ```

3. **Test transaction endpoint**:
   ```bash
   curl -X PUT \
     -H "Authorization: Bearer TMCP_HS_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"events": [{"type": "m.room.message", ...}]}' \
     https://tmcp.tween.im/_matrix/app/v1/transactions/test
   ```

4. **Verify network connectivity**:
   ```bash
   # From homeserver container
   docker exec matrix-synapse curl -f http://tmcp-server:3000/_matrix/app/v1/ping
   # Response should be: {"duration_ms": 123}
   ```

### Namespace Conflicts

**Symptom**: Error about namespace already registered.

**Check**:
```bash
docker exec matrix-synapse ls /data/*.yaml
# Look for other AS registrations with similar namespaces
```

**Solution**:
- Ensure `id: tween-miniapps` is unique
- Check namespace regexes don't overlap with other bridges

### Token Errors

**Symptom**: `401 Unauthorized` or `403 Forbidden` errors.

**Check**:

1. **Verify AS token matches registration**:
   ```yaml
   # In registration file
   as_token: "{{ matrix_synapse_tmcp_appservice_token }}"

   # In inventory file
   matrix_synapse_tmcp_appservice_token: "54280d60..."
   ```

2. **Verify HS token in TMCP server configuration**:
   - TMCP Server must use exact same token from registration

3. **Test authorization**:
   ```bash
   curl -H "Authorization: Bearer HS_TOKEN_HERE" \
     https://tmcp.tween.im/_matrix/app/v1/ping
   ```

---

## Quick Reference

### Files and Locations

| File | Path | Purpose |
|-------|--------|---------|
| Registration | `/data/tmcp-registration.yaml` | AS configuration |
| Inventory | `inventory/host_vars/core.tween.im/vars.yml` | Tokens and AS config |
| Role defaults | `roles/custom/matrix-tmcp-integration/defaults/main.yml` | Registration template |
| Synapse config | `/data/homeserver.yaml` | Loads registration |

### Useful Commands

```bash
# Reload Synapse configuration
docker exec matrix-synapse kill -HUP 1

# Check registration status
docker exec matrix-synapse cat /data/tmcp-registration.yaml

# View Synapse logs
docker logs matrix-synapse -f --tail 100

# Test AS ping (from homeserver)
curl -X POST \
  -H "Authorization: Bearer HS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "test"}' \
  http://tmcp-server:3000/_matrix/app/v1/ping

# Test AS ping (from AS perspective)
curl -X POST \
  -H "Authorization: Bearer AS_TOKEN" \
  -d '{"transaction_id": "test"}' \
  https://core.tween.im/_matrix/client/v3/appservices/tween-miniapps/ping

# Check if bot user exists
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  https://core.tween.im/_matrix/client/v3/profile/@_tmcp_payments:tween.im

# List all rooms AS user is in
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  https://core.tween.im/_matrix/client/v3/joined_rooms
```

---

## Further Reading

- [TMCP Protocol Specification (PROTO.md)](../../PROTO.md) - Full protocol documentation
- [Matrix Application Service API v1.11](https://spec.matrix.org/v1.11/application-service-api/) - Official spec
- [Synapse Application Service Documentation](https://element-hq.github.io/synapse/latest/application_services.html) - Synapse-specific details

---

## Support

For issues with this integration:
1. Check Synapse logs: `docker logs matrix-synapse`
2. Check TMCP Server logs: `docker logs tmcp-server` (if running)
3. Review namespace configuration in this guide
4. Verify MAS OAuth client is properly configured
