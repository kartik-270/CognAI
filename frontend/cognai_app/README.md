# CognAI Mobile Interface

This is the primary Flutter application (iOS & Android) for the CognAI Cognitive Companion. 
It is built strictly adhering to the **Luminous Minimal** design system, ensuring a "Quiet Premium" aesthetic focusing on exceptionally crisp typography, expansive whitespace, and minimal UI elements.

## Core Features

- **Native Google Auth**: Apple App-Store compliant native Google Sign-In, coupled with JWT storage.
- **Virtual Scrolling Chat**: A highly optimized `ListView` capable of rendering 100+ session memory histories without dropping frames.
- **Resilient WebSockets**: The chat interface connects to the FastAPI backend via WebSockets. It features an **offline message queue** and automatic exponential reconnection if the connection drops.
- **Metacognitive Loading UI**: Rather than generic spinners, the app uses sophisticated skeleton shimmer screens and explicit *"CognAI is thinking deeply..."* indicators when the backend triggers a `slow_think` state.

## Architecture (Feature-First)

The app avoids generic layer-based folders (like `models/`, `views/`) to prevent circular dependencies. Instead, it uses a Feature-First structure:

```text
lib/
├── core/
│   ├── network/           # Dio REST client, WebSocket queue manager
│   ├── theme.dart         # Luminous Minimal colors, shapes, and typography
│   └── routing/           # go_router configuration
├── features/
│   ├── auth/              # Login, Register, Google OAuth UI
│   ├── chat/              # WebSocket interface, message bubbles
│   └── memory/            # Episodic feed and Persona visual sliders
└── shared/
    └── widgets/           # Reusable minimal buttons, shimmer skeletons
```

## State Management

We use **Riverpod** (`flutter_riverpod`) for Dependency Injection and State Management. It is particularly effective at handling the asynchronous WebSocket streams (`StreamProvider`) that drive the chat UI.

## Getting Started

1. Ensure the Flutter SDK is installed on your system.
2. Navigate to this directory and install dependencies:
   ```bash
   flutter pub get
   ```
3. *(Optional)* If you are generating specific Riverpod or Freezed code (future use):
   ```bash
   flutter pub run build_runner build --delete-conflicting-outputs
   ```
4. Run the application:
   ```bash
   flutter run
   ```

## To run on android device 

path to adb in android : 
for ex : C:\Users\karti\AppData\Local\Android\Sdk\platform-tools\adb.exe   
command to pair : 
C:\Users\karti\AppData\Local\Android\Sdk\platform-tools\adb.exe pair <IP_ADDRESS>

command to connect :
C:\Users\karti\AppData\Local\Android\Sdk\platform-tools\adb.exe connect [IP_ADDRESS]

flutter run


*Note: Ensure the FastAPI backend and its PostgreSQL/Neo4j databases are running locally before attempting to log in.*
