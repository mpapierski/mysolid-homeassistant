# MySolid Mobile API Reverse-Engineering Notes

## Scope

- Source analyzed: `pl.unityt.msc.android` from APKPure, version `3.5.3 (2015)`, versionCode `30503`.
- Method: unpacked the APKPure XAPK, decompiled the base APK with JADX, then inspected Retrofit interfaces, DTOs, Firebase code, and UI code that interprets responses.
- Status: this document is based on static analysis of the app code. Field names and endpoint paths are code-derived. Exact runtime date formatting and some status-code behavior should still be confirmed against live traffic.

## Quick Answer: Locked vs Unlocked

The app models the alarm state as `armed` / `disarmed`.

The primary endpoint is:

- `GET /api/v1.3/property-details`

Meaning of `propertyDetails[].armed`:

- `true`: alarm armed, UI shows a red bar and a lock icon
- `false`: alarm disarmed, UI shows a green bar and an unlock icon
- `null`: unknown state

Example response shape:

```json
{
  "clientId": 123456,
  "propertyDetails": [
    {
      "id": 987654,
      "name": "Home",
      "externalId": "ABCD1234",
      "address": {
        "state": "MAZOWIECKIE",
        "code": "00-001",
        "city": "Warszawa",
        "street": "Przykladowa",
        "number": "1"
      },
      "armed": true,
      "convoysEnabled": true,
      "camerasEnabled": true,
      "cameras": []
    }
  ]
}
```

If you need a more control-oriented state model, the app also uses:

- `GET /api/v1.3/transmitters/relaysWithPin?accountId=<propertyDetails.id>`

Relay states include:

- `ARM`
- `DISARM`
- `PARTIAL_ARM`
- `ON`
- `OFF`
- `UNDEFINED`

## Base URLs

- Polish: `https://mysolid.solidsecurity.pl/`
- Czech: `https://mysolid.solidsecurity.cz/`

`BuildConfig.HOST` and `BuildConfig.SERVER` both point to the Polish host by default.

## Common Protocol Details

### Auth model

The app has two Retrofit interfaces:

- pre-auth / account setup:
  - `POST /api/authorization`
  - `PUT /changeUserPassword`
  - `POST /mobile/register`
  - `POST /mobile/resetPassword`
- authenticated service API:
  - everything under `MySolidServiceApiInterface`

The login response is an `AccessToken` object:

```json
{
  "value": "raw-access-token-string",
  "expiration": "2026-03-16T12:34:56.000Z"
}
```

Important: the app sends `Authorization: <token>` exactly as returned. No `Bearer ` prefix is added.

### Default headers

Authenticated calls add these headers:

- `Accept: application/json`
- `Authorization: <AccessToken.value>`
- `CurrentAppVersionName: 3.5.3 (2015)`
- `CurrentAppVersionCode: 30503`
- `CurrentAppPhoneName: <Build.BRAND>`
- `CurrentAppPhoneVersion: <Build.MODEL>`
- `CurrentAppPhoneOsVersion: <Build.VERSION.RELEASE>`
- `UserEmail: <email>` when available
- `CurrentAppPhoneDeviceId: <derived device id>`

The app also enables `HttpLoggingInterceptor(Level.BODY)` in release.

### Device ID derivation

`CurrentAppPhoneDeviceId` is derived as follows:

- Android 10+ (`SDK_INT >= 29`): `ANDROID_ID#<android_id>`
- older Android with `READ_PHONE_STATE`: IMEI if available, otherwise `android_id`
- older Android without permission: empty string

### Serialization notes

- Retrofit uses Jackson.
- The app DTOs use a mix of `Date`, Joda `DateTime`, Joda `LocalTime`, and Joda `LocalDateTime`.
- JSON examples in this document use readable ISO-like values. Treat them as field-name maps, not as a guaranteed wire-format sample.

## Identifier Semantics

The naming in the app is inconsistent. These are the important ID mappings:

| Field | Meaning | Used by |
| --- | --- | --- |
| `clientId` | top-level customer/client identifier | property details, relay user details, push payloads |
| `propertyDetails[].id` | primary property/account identifier | used as `accountId` and also as `propertyId` in many calls |
| `propertyDetails[].externalId` | external property identifier | used by suspension APIs |
| `eventId` | active or historical event identifier | alarm cancel, event listings |
| `eventBundleId` | push/alarm acknowledgement identifier | `PUT /api/alarms/confirm` |
| `deviceId` | device identifier used for auth, Firebase, biometrics | sign-in, Firebase token endpoints, biometric endpoints |

Important inconsistency:

- `CreateSuspensionDto.accountExternalId` is a misleading field name.
- In app logic, it appears to be populated with the selected property/account `id` converted to string, not with `externalId`.

## Sensitive Data Exposed by the App

`GET /api/v1.3/property-details` returns more than just armed status. Each property can include camera connection details:

```json
{
  "serialNumber": "CAM123",
  "address": "10.0.0.15",
  "port": "8000",
  "username": "camera-user",
  "password": "camera-password",
  "channels": [
    {
      "name": "Front Gate",
      "number": 1,
      "ptz": false
    }
  ],
  "rstpPort": "554",
  "protocol": "RTSP"
}
```

So the mobile API surface exposes:

- alarm armed/disarmed state
- account/property names and addresses
- convoy/camera enablement flags
- camera hostnames, ports, usernames, and passwords

## Endpoint Inventory

### Authentication and Account Lifecycle

| Method | Path | Meaning | Request payload | Response payload |
| --- | --- | --- | --- | --- |
| `POST` | `/api/authorization` | sign in | `email`, `password`, `deviceId`, `deviceName`, optional deprecated `firebaseToken` | `value`, `expiration` |
| `PUT` | `/changeUserPassword` | change account password | `email`, `oldPasswd`, `newPasswd` | no body |
| `POST` | `/mobile/register` | create/register account | `clientNumber`, `clientType`, `email`, `name`, `phone`, `surname`, `address`, `flagAndroid` | no body |
| `POST` | `/mobile/resetPassword` | start password reset | `emailAddress`, `flagAndroid` | no body |
| `DELETE` | `/api/deleteUser` | delete current user | no body | no body |
| `HTTP DELETE` | `/api/firebase/delete` | logout/unregister current device from push | `deviceId` | no body |
| `PUT` | `/api/firebase/token` | upload/refresh Firebase token | `deviceId`, `newFirebaseToken` | no body |

Login example:

```json
{
  "email": "user@example.com",
  "password": "secret",
  "deviceId": "ANDROID_ID#7d8a9b0c",
  "deviceName": "Pixel 8",
  "firebaseToken": "optional-or-null"
}
```

Login success example:

```json
{
  "value": "7f3345b0-....",
  "expiration": "2026-03-16T12:34:56.000Z"
}
```

Login error body used by the app:

```json
{
  "errorCode": 4,
  "lockTimeMs": 300000
}
```

Observed auth error codes:

- `1`: device is not authorized
- `2`: bad credentials
- `3`: device blocked
- `4`: login locked

### Property, Account, Permission, and Relay State

| Method | Path | Meaning | Request payload | Response payload |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1.3/property-details` | fetch account/property list and high-level state | none | `clientId`, `propertyDetails[]` |
| `GET` | `/api/permissions` | fetch feature permissions | none | `Set<String>` |
| `GET` | `/api/v1.3/transmitters/relaysWithPin?accountId=<id>` | fetch relay/arming controls for an account | query: `accountId` | `List<MobileTransmitterRelayWithStateDtoV13>` |
| `PUT` | `/api/v1.3/transmitters/relays/updateState` | change relay/arming state | relay update DTO | no body |
| `PUT` | `/api/v1.3/transmitters/relays/update` | change relay metadata and possibly state | relay update DTO | no body |

`GET /api/v1.3/property-details` response shape:

```json
{
  "clientId": 123456,
  "propertyDetails": [
    {
      "id": 987654,
      "name": "Home",
      "externalId": "ABCD1234",
      "address": {
        "state": "MAZOWIECKIE",
        "code": "00-001",
        "city": "Warszawa",
        "street": "Przykladowa",
        "number": "1"
      },
      "armed": false,
      "convoysEnabled": true,
      "camerasEnabled": true,
      "cameras": [
        {
          "serialNumber": "CAM123",
          "address": "10.0.0.15",
          "port": "8000",
          "username": "camera-user",
          "password": "camera-password",
          "channels": [
            {
              "name": "Front Gate",
              "number": 1,
              "ptz": false
            }
          ],
          "rstpPort": "554",
          "protocol": "RTSP"
        }
      ]
    }
  ]
}
```

Observed permission strings checked by the UI:

- `CAMERAS`
- `EVENT_SUSPENSION`
- `SERVICE_AND_SUPERVISION_COMMISSIONING`
- `AUTHORIZED_USERS`
- `CONVOYS`

Relay response shape:

```json
[
  {
    "transmitterId": 1111,
    "number": 1,
    "label": "Alarm",
    "state": "ARM",
    "changeStatusDate": "2026-03-16T12:00:00.000Z",
    "requestedState": "DISARM",
    "changeStatus": "WAITING",
    "type": "BISTABLE",
    "stateSet": "ARM2",
    "waitingForEvent": true,
    "relayPinConfirmation": true,
    "iconName": "lock",
    "iconNameOff": "lock_open"
  }
]
```

Relay update request shape:

```json
{
  "user": {
    "webUserId": 555,
    "clientId": 123456,
    "email": "user@example.com",
    "phone": "+48123123123"
  },
  "account": {
    "accountId": 987654,
    "accountExternalId": "ABCD1234"
  },
  "transmitterId": 1111,
  "relayId": 2222,
  "relayNumber": 1,
  "state": "DISARM",
  "label": "Alarm",
  "iconName": "lock",
  "iconNameOff": "lock_open",
  "pin": "1234"
}
```

Important relay enums:

- `MobileRelayStateEnum`: `ON`, `OFF`, `ARM`, `DISARM`, `PARTIAL_ARM`, `UNDEFINED`
- `MobileRelayStateSetDto`: `ON_OFF`, `ARM2`, `ARM3`
- `MobileRelayChangeStatusDto`: `ERROR`, `SUCCESS`, `WAITING`, `SUCCESS_NO_EVENT`
- `MobileTransmitterRelayTypeEnum`: `MONOSTABLE`, `BISTABLE`

### Alarms, Amber, and Event History

| Method | Path | Meaning | Request payload | Response payload |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1.4/alarms` | list active alarms | none | `List<AlarmEventV16>` |
| `POST` | `/api/alarms` | create/report alarm event | `propertyId`, optional `location`, optional `type` | `authorized` |
| `HTTP DELETE` | `/api/alarms` | cancel alarm | `eventId`, optional `pin` | `forced` |
| `PUT` | `/api/alarms/confirm` | acknowledge push/alarm event bundle | `eventBundleId` | no body |
| `POST` | `/api/ambers` | create amber/escort request | `propertyId`, optional `location`, optional `type`, `durationMilliseconds` | `amberId`, `dateTime` |
| `HTTP DELETE` | `/api/ambers` | cancel amber | `amberId`, optional `pin` | `amberId` |
| `GET` | `/api/historical-events/{propertyId}?page=<n>&size=<n>` | historical events for one property/account | path `propertyId`, query `page`, `size` | `page`, `size`, `historicalEvents[]` |

Alarm report request example:

```json
{
  "propertyId": 987654,
  "location": {
    "lon": 21.0122,
    "lat": 52.2297
  },
  "type": "ALARM"
}
```

Alarm report response:

```json
{
  "authorized": true
}
```

Alarm cancel request:

```json
{
  "eventId": 444444,
  "pin": "1234"
}
```

Alarm cancel response:

```json
{
  "forced": false
}
```

Amber request example:

```json
{
  "propertyId": 987654,
  "type": "POSITIONED_ALERT",
  "location": {
    "lon": 21.0122,
    "lat": 52.2297
  },
  "durationMilliseconds": 900000
}
```

Amber response:

```json
{
  "amberId": "AMBER-123",
  "dateTime": "2026-03-16T12:34:56.000Z"
}
```

Active alarm list item shape:

```json
{
  "propertyDetails": {
    "id": 987654,
    "name": "Home"
  },
  "eventId": 444444,
  "eventStatusType": "OPENED",
  "group": "ALARM",
  "label": "Intrusion",
  "receiveDate": "2026-03-16T12:34:56.000Z",
  "sourceId": 12,
  "sourceName": "Panel",
  "partitionNumber": 1,
  "partitionName": "Ground floor",
  "position": {
    "lat": 52.2297,
    "lon": 21.0122
  },
  "cancellable": true
}
```

Historical event response shape:

```json
{
  "page": 0,
  "size": 20,
  "historicalEvents": [
    {
      "eventId": 444444,
      "eventBundleId": 333333,
      "group": "ALARM",
      "description": "Intrusion detected",
      "receiveDate": "2026-03-16T12:34:56.000Z",
      "partition": "Ground floor",
      "transmitterAddress": "123456",
      "code": "130",
      "source": "Panel",
      "suspended": false
    }
  ]
}
```

Observed alarm enums:

- `AlarmTypeEnum`: `ALARM`, `OPEN`, `CLOSE`, `POSITIONED_MEDICAL_ALERT`, `POSITIONED_ALERT`
- `AlarmEvent.EventStatusType`: `CANCELLED`, `OPENED`, `CLOSED`

### Authorized Users and Account Administration

| Method | Path | Meaning | Request payload | Response payload |
| --- | --- | --- | --- | --- |
| `GET` | `/api/authorizedUsers?accountId=<id>` | list authorized users for an account | query: `accountId` | `List<AuthorizedUserMySolidEsimonDto>` |
| `GET` | `/api/authorizedUsers/phoneTypesAndSinglePropertyRoles?accountId=<id>` | fetch available phone types and roles | query: `accountId` | `roles[]`, `phoneTypes[]` |
| `POST` | `/api/authorizedUsers` | create authorized user | authorized-user DTO | no body |
| `PUT` | `/api/authorizedUsers` | edit authorized user | authorized-user DTO | no body |
| `DELETE` | `/api/authorizedUsers/{id}` | delete authorized user | path `id` | no body |
| `PUT` | `/api/authorizedUsers/resetPasswordAuthorizedUser` | reset authorized user password/PIN flow | `id`, `pin` | no body |
| `PUT` | `/api/authorizedUsers/changeOrder?accountId=<id>` | update display/order of authorized users | query: `accountId`, body list of IDs | no body |

Authorized user list item shape:

```json
{
  "id": 777,
  "authorizedUserRoleName": "Owner",
  "authorizedUserRoleId": 10,
  "name": "Jan",
  "surname": "Kowalski",
  "comment": "Primary contact",
  "order": 1,
  "temporary": false,
  "activeFrom": "2026-03-01T00:00:00.000Z",
  "activeTo": "2026-12-31T23:59:59.000Z",
  "confirmed": true,
  "expireSoon": false,
  "phonesList": [
    {
      "phoneNumber": "+48123123123",
      "order": 1,
      "type": "SMS"
    }
  ],
  "emailsList": [
    {
      "email": "jan@example.com",
      "order": 1,
      "type": "MAIN"
    }
  ]
}
```

Create/edit authorized user request shape:

```json
{
  "id": 777,
  "accountId": 987654,
  "roleId": 10,
  "name": "Jan",
  "surname": "Kowalski",
  "number": "+48123123123",
  "comment": "Primary contact",
  "phonesList": [
    {
      "phoneNumber": "+48123123123",
      "order": 1,
      "type": "SMS"
    }
  ],
  "email": "jan@example.com",
  "temporary": false,
  "activeFrom": "2026-03-01T00:00:00.000Z",
  "activeTo": "2026-12-31T23:59:59.000Z",
  "soonToExpire": 0,
  "pin": "1234"
}
```

Role/phone-type metadata shape:

```json
{
  "roles": [
    {
      "id": 10,
      "name": "Owner",
      "description": "Full access",
      "authorizedUserAccessLevelEsimonSinglePropertyEnum": "FULL",
      "availableForCustomer": true
    }
  ],
  "phoneTypes": [
    {
      "description": "SMS",
      "type": "SMS"
    }
  ]
}
```

Reset password/PIN request for an authorized user:

```json
{
  "id": 777,
  "pin": "1234"
}
```

Change order request body:

```json
[777, 778, 779]
```

### Schedules, Suspensions, and Additional Services

| Method | Path | Meaning | Request payload | Response payload |
| --- | --- | --- | --- | --- |
| `GET` | `/api/schedules?accountId=<id>` | fetch schedules for account and transmitters/partitions | query: `accountId` | `MobileAccountSchedulesDto` |
| `PUT` | `/api/schedules/range` | update normal schedule range | `target`, `accountId`, `transmitterId`, `partitionNumber`, `scheduleBefore`, `scheduleAfter` | no body |
| `PUT` | `/api/schedules/special` | create/update special schedule ranges | `target`, `accountId`, `transmitterId`, `partitionNumber`, `ranges[]` | no body |
| `DELETE` | `/api/schedules/special/{id}` | delete special schedule range | path `id` | no body |
| `GET` | `/api/mobile/suspension/v2?externalPropertyId=<id>` | list event suspensions for a property | query: `externalPropertyId` | `List<SuspensionListDto>` |
| `POST` | `/api/mobile/suspension` | create event suspension | `suspendFrom`, `suspendUntil`, `externalPropertyId`, `accountExternalId` | no body |
| `DELETE` | `/api/mobile/suspension?eventSuspensionId=<id>` | delete event suspension | query: `eventSuspensionId` | no body |
| `GET` | `/api/additional-contact-services` | fetch contact-service types | none | `serviceTypes[]` |
| `GET` | `/api/v1.2/additional-services` | fetch additional service types | none | `serviceTypes[]` |
| `GET` | `/api/v1.2/additional-services/{propertyId}` | list additional services for a property/account | path `propertyId` | `additionalServices[]` |
| `POST` | `/api/v1.2/additional-services` | order a new additional service | `accountId`, `type`, `description`, `serviceDate` | created service DTO |
| `GET` | `/api/fivestars` | should the app show rating dialog | none | boolean |
| `PUT` | `/api/fivestars` | store "user rated app" flag | `isRated` | no body |

Schedule response shape:

```json
{
  "accountId": 987654,
  "name": "Home",
  "schedule": {
    "ranges": [
      {
        "day": "MONDAY",
        "opened": "08:00:00",
        "closed": "18:00:00",
        "earlyOpen": 0,
        "lateOpen": 0,
        "earlyClose": 0,
        "lateClose": 0,
        "modifiedDateTime": "2026-03-16T12:00:00.000Z",
        "modifiedByWebUser": {
          "id": 555,
          "email": "admin@example.com"
        }
      }
    ],
    "specialRanges": [
      {
        "id": 1,
        "from": "2026-12-24T00:00:00",
        "to": "2026-12-26T23:59:59",
        "addedTime": "2026-03-16T12:00:00.000Z",
        "addedByWebUser": {
          "id": 555,
          "email": "admin@example.com"
        },
        "comment": "Christmas"
      }
    ]
  },
  "transmitters": [
    {
      "transmitterId": 1111,
      "address": "123456",
      "schedule": {
        "ranges": [],
        "specialRanges": []
      },
      "partitions": [
        {
          "number": 1,
          "label": "Ground floor",
          "schedule": {
            "ranges": [],
            "specialRanges": []
          }
        }
      ]
    }
  ]
}
```

Normal schedule change request:

```json
{
  "target": "PARTITION",
  "accountId": 987654,
  "transmitterId": 1111,
  "partitionNumber": 1,
  "scheduleBefore": {
    "day": "MONDAY",
    "opened": "08:00:00",
    "closed": "18:00:00",
    "earlyOpen": 0,
    "lateOpen": 0,
    "earlyClose": 0,
    "lateClose": 0
  },
  "scheduleAfter": {
    "day": "MONDAY",
    "opened": "09:00:00",
    "closed": "17:00:00",
    "earlyOpen": 0,
    "lateOpen": 0,
    "earlyClose": 0,
    "lateClose": 0
  }
}
```

Special schedule request:

```json
{
  "target": "ACCOUNT",
  "accountId": 987654,
  "transmitterId": 0,
  "partitionNumber": 0,
  "ranges": [
    {
      "from": "2026-12-24T00:00:00",
      "to": "2026-12-26T23:59:59",
      "comment": "Christmas"
    }
  ]
}
```

Suspension request:

```json
{
  "suspendFrom": "2026-03-16T12:00:00.000Z",
  "suspendUntil": "2026-03-16T18:00:00.000Z",
  "externalPropertyId": "ABCD1234",
  "accountExternalId": "987654"
}
```

Suspension list item:

```json
{
  "suspendFrom": "2026-03-16T12:00:00.000Z",
  "suspendUntil": "2026-03-16T18:00:00.000Z",
  "eventSuspensionId": 123,
  "externalPropertyId": "ABCD1234",
  "suspensionFrom": "APP",
  "suspensionCreator": "user@example.com",
  "archived": false,
  "cancellationDate": null,
  "cancellationFrom": null,
  "cancellationCreator": null
}
```

Additional service type/list shapes:

```json
{
  "serviceTypes": [
    {
      "id": 1,
      "name": "Serwis"
    }
  ]
}
```

```json
{
  "additionalServices": [
    {
      "id": 10,
      "createTime": "2026-03-16T12:00:00.000Z",
      "description": "Please check sensor",
      "accountId": 987654,
      "type": {
        "id": 1,
        "name": "Serwis"
      },
      "serviceDate": "2026-03-20T09:00:00.000Z"
    }
  ]
}
```

New additional service request:

```json
{
  "accountId": 987654,
  "type": {
    "id": 1,
    "name": "Serwis"
  },
  "description": "Please check sensor",
  "serviceDate": "2026-03-20T09:00:00.000Z"
}
```

Rating payload:

```json
{
  "isRated": true
}
```

### PIN, Secure Views, Biometrics, and Push-Related APIs

| Method | Path | Meaning | Request payload | Response payload |
| --- | --- | --- | --- | --- |
| `GET` | `/api/pin/{pin}` | validate PIN | path `pin` | no body |
| `PUT` | `/api/pin` | change PIN | `oldPin`, `newPin` | no body |
| `PUT` | `/api/pin/reset` | reset PIN | none | no body |
| `GET` | `/api/pinSecuredActions/pinSettings` | fetch PIN failure settings/state | none | `blocked`, `mistakesAllowed`, `maxMistakesAllowed`, `updateDate` |
| `PUT` | `/api/pinSecuredActions/pinSettings` | store PIN failure settings/state | same object | no body |
| `GET` | `/api/pinSecuredActions/v2.0` | fetch per-view PIN requirements | none | `pinSecuredActionDtos[]` |
| `POST` | `/api/pinSecuredActions/v2.0` | update per-view PIN requirements | `pinSecuredActionDtos[]` | no body |
| `GET` | `/api/pinSecuredActions/v2.0/checkAction?pinSecuredActionsEnum=<enum>` | check one secure-view rule | query enum | `pinSecuredActionsEnum`, `pinSecured` |
| `POST` | `/api/pinSecuredActions/checkPin/v2.0` | validate PIN for one secure action | `pinSecuredActionsEnum`, `pinValue` | `pinCorrect`, `mistakesAllowed`, `timeLeftBeforeNextAttemptsInMilliSeconds` |
| `POST` | `/api/biometricAuth/challenge` | get biometric challenge | `deviceId` | `challenge` |
| `POST` | `/api/biometricAuth` | upload biometric public key | `deviceId`, `publicKey` | no body |
| `POST` | `/api/biometricAuth/verify` | verify biometric signature | `deviceId`, `challenge`, `signature`, `isAuthForSecureView` | no body |
| `DELETE` | `/api/biometricAuth/{deviceId}` | delete biometric public key for device | path `deviceId` | no body |
| `POST` | `/api/firebase/confirm` | confirm push receipt/read | `messageId`, `receivedDate` | no body |

PIN change request:

```json
{
  "oldPin": "1234",
  "newPin": "5678"
}
```

PIN settings response:

```json
{
  "blocked": false,
  "mistakesAllowed": 3,
  "maxMistakesAllowed": 3,
  "updateDate": "2026-03-16T12:00:00.000Z"
}
```

Secure-view list response:

```json
{
  "pinSecuredActionDtos": [
    {
      "pinSecuredActionsEnum": "VIEW_CAMERAS",
      "pinSecured": true
    },
    {
      "pinSecuredActionsEnum": "VIEW_EVENT_HISTORY",
      "pinSecured": false
    }
  ]
}
```

Secure-view PIN check request:

```json
{
  "pinSecuredActionsEnum": "VIEW_CAMERAS",
  "pinValue": "1234"
}
```

Secure-view PIN check response:

```json
{
  "pinCorrect": true,
  "mistakesAllowed": 3,
  "timeLeftBeforeNextAttemptsInMilliSeconds": 0
}
```

Supported secure-action enums in V2:

- `VIEW_ACTIVE_ALARMS`
- `VIEW_CAMERAS`
- `VIEW_PROTECTED_PROPERTIES`
- `VIEW_EVENT_HISTORY`
- `VIEW_AUTHORIZED_USER_LIST`
- `VIEW_ADD_AUTHORIZED_USER`
- `VIEW_EDIT_AUTHORIZED_USER`
- `VIEW_DELETE_AUTHORIZED_USER`
- `VIEW_ORDER_NEW_SERVICE`
- `VIEW_SETTINGS`
- `VIEW_CHANGE_PASSWORD`
- `VIEW_TRANSMITTERS`
- `VIEW_CONTACT`
- `VIEW_SUSPENSIONS`
- `UNKNOWN`

Biometric payloads:

```json
{
  "deviceId": "ANDROID_ID#7d8a9b0c"
}
```

```json
{
  "challenge": "base64-or-random-string"
}
```

```json
{
  "deviceId": "ANDROID_ID#7d8a9b0c",
  "publicKey": "base64-public-key"
}
```

```json
{
  "deviceId": "ANDROID_ID#7d8a9b0c",
  "challenge": "base64-or-random-string",
  "signature": "base64-signature",
  "isAuthForSecureView": true
}
```

Push confirmation payload:

```json
{
  "messageId": "firebase-message-id",
  "receivedDate": "2026-03-16T12:34:56.000Z"
}
```

## Firebase / Push Notification Model

The app can update local state from Firebase without polling.

Incoming FCM data payload behavior:

- reads `data.message`
- base64-decodes it
- uses the access token to derive the AES key
- decrypts first 16 bytes with AES-ECB to obtain the IV
- decrypts the remainder with AES-CBC
- deserializes the JSON into a polymorphic `Notification`

Observed notification subclasses:

- `AlarmNotification`
- `ClientDetailsNotification`
- `AppVersionNotification`
- `SessionExpiredNotification`
- `RearmingNotification`
- `FirebaseHandshakeNotification`
- `PropertyDetailsNotification`
- `RelayNotification`

This matters because `PropertyDetailsNotification` can carry armed/disarmed state updates:

```json
{
  "clientId": 123456,
  "propertiesDetails": [
    {
      "id": 987654,
      "name": "Home",
      "externalId": "ABCD1234",
      "address": {
        "state": "MAZOWIECKIE",
        "code": "00-001",
        "city": "Warszawa",
        "street": "Przykladowa",
        "number": "1"
      },
      "armed": true
    }
  ]
}
```

Observed push-related click-action strings:

- `pl.unityt.msc.android.MainActivity.ACTION_SHOW_ACTIVE_ALARMS`
- `pl.unityt.msc.android.REARMING_CLICK_ACTION`
- `pl.unityt.msc.android.RELOAD_RELAY_CLICK_ACTION`
- `pl.unityt.msc.android.ACTION_SESSION_EXPIRED`
- `pl.unityt.msc.android.WATCH_NOTIFICATION_CLICK_ACTION`
- `pl.unityt.msc.android.INVOICE_CLICK_ACTION`

`RelayNotification` payload shape:

```json
{
  "title": "Relay updated",
  "body": "Alarm disarmed",
  "clickAction": "pl.unityt.msc.android.RELOAD_RELAY_CLICK_ACTION",
  "mobileRelayExecute": [
    {
      "relayDto": {
        "id": 2222,
        "number": 1,
        "label": "Alarm",
        "state": "DISARM",
        "waitingForEvent": false,
        "changeStatusDate": "2026-03-16T12:34:56.000Z",
        "transmitterRelayType": "BISTABLE"
      },
      "state": "DISARM",
      "changeStatus": "SUCCESS"
    }
  ]
}
```

`AlarmNotification` payload shape:

```json
{
  "alarmEvent": {
    "eventId": 444444,
    "group": "ALARM",
    "label": "Intrusion"
  }
}
```

## Practical Minimal Flow

If the only goal is to determine whether the alarm is currently locked/unlocked and collect account metadata, the shortest useful flow is:

1. `POST /api/authorization`
2. `GET /api/v1.3/property-details`
3. For each property:
   - use `armed` for current lock/unlock state
   - use `id` as the main `accountId`/`propertyId` in later calls
   - use `externalId` for suspension calls
4. Optionally enrich with:
   - `GET /api/permissions`
   - `GET /api/authorizedUsers?accountId=<id>`
   - `GET /api/v1.3/transmitters/relaysWithPin?accountId=<id>`
   - `GET /api/historical-events/<id>?page=0&size=20`
   - `GET /api/schedules?accountId=<id>`

## Notes and Open Questions

- Date and time field names are known, but exact wire formatting should be verified against real requests or server responses.
- `CreateSuspensionDto.accountExternalId` appears misnamed in the client and should be tested carefully before relying on it.
- Some nested DTOs used inside push-only relay execution payloads were not fully expanded here because they are not needed for the main armed/disarmed state workflow.
