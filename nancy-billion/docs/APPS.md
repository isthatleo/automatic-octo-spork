# Billion apps — Windows, macOS, Linux, Android, iOS

Every Billion app is a window onto the same running stack. There is no separate
mobile backend and no cloud tenancy: the app finds your machine, loads the
control room, and everything — tools, memory, agents, voice — runs where it
always did. Start the stack first, on the machine that holds your data:

```
docker compose up -d
```

That serves the control room on port 3005 and the backend on 8000. All five
apps below point at exactly that.

## The zero-build option: install from the browser

The control room ships a PWA manifest, so before touching any build tooling you
can install it as a real app on every platform in about ten seconds:

| Platform | How |
| --- | --- |
| Windows, macOS, Linux | Open `http://localhost:3005` in Chrome or Edge, then the install icon in the address bar |
| Android | Open the control room in Chrome, then **Install app** |
| iOS / iPadOS | Open it in Safari, then **Share → Add to Home Screen** |

Installed this way it runs in its own window with the reactor icon, no browser
chrome, straight into the voice-first hero. For most day-to-day use this is all
you need. Build the native apps when you want a real installer to hand around,
an app-store-shaped artifact, or the native splash and app-switcher identity.

## Native builds

One command per platform. The first run downloads Electron or Capacitor, so
give it a few minutes and a working network connection.

**Windows** (PowerShell, from the repo root):

```powershell
.\scripts\build-apps.ps1            # desktop installer + portable .exe
.\scripts\build-apps.ps1 android    # Android project, then opens Android Studio
.\scripts\build-apps.ps1 all
```

**macOS and Linux**:

```bash
./scripts/build-apps.sh             # .dmg on macOS; AppImage + .deb on Linux
./scripts/build-apps.sh android
./scripts/build-apps.sh ios         # macOS only
./scripts/build-apps.sh all
```

Desktop artifacts land in `desktop/dist/`. The script prints the file names when
it finishes.

### What each target needs

Nothing beyond Node 18+ for the desktop apps. `electron-builder` produces an
NSIS installer plus a portable exe on Windows, a `.dmg` on macOS, and an
AppImage plus `.deb` on Linux. It builds for the OS you are standing on —
cross-compiling to macOS from Windows is not supported by Apple's toolchain.

Android additionally needs Android Studio, which supplies the SDK and the
emulator. The script generates `mobile/android`, applies the icon set, and opens
the project; pressing **Run** launches the emulator with Billion in it.

iOS needs macOS with Xcode and CocoaPods. The script generates `mobile/ios`,
patches `Info.plist` with the App Transport Security exception that plain-http
LAN traffic requires, and opens the workspace; pressing **Run** launches the
simulator.

## How the mobile apps find your machine

This used to be a hardcoded IP address in `capacitor.config.json`, which broke
the moment you changed networks. It now resolves itself at launch: the app tries
the host it used last, then the emulator loopbacks (`10.0.2.2` on Android,
`localhost` on the iOS simulator), and only asks if none of them answer. Type
your machine's LAN address once — `ipconfig` on Windows, `ifconfig` on
macOS/Linux — and it is remembered from then on. Port 3005 is assumed unless you
type a different one.

On a physical phone, the phone and the machine running the stack have to be on
the same network. Nothing is routed through the internet.

## Icons

All app icons are drawn procedurally by `scripts/gen_icons.py` from a single
definition of the reactor mark, so any size can be regenerated without hunting
for a master file:

```
python scripts/gen_icons.py
```

That writes the desktop icon, the web/PWA set including a maskable variant, and
the 1024px mobile icon and splash that `@capacitor/assets` expands into every
Android and iOS density.

## Troubleshooting

**The desktop app shows a spinning reactor and "waiting for the control room".**
The stack isn't up. Run `docker compose up -d` and it connects on its own within
a few seconds — no need to restart the app.

**The mobile app keeps asking for a host.** Nothing is answering on port 3005 at
the address you gave. Check the stack is running, check you typed the machine's
LAN address rather than `localhost` (on a physical phone, `localhost` is the
phone), and check both devices are on the same network.

**`npm install` fails on a corporate or filtered network.** Both build scripts
need the public npm registry for the first run only. After that the installs are
cached and the builds work offline.
