/*
 * KTOx Remote Control - M5Stack Cardputer
 * =========================================
 * Complete remote control for KTOX_Pi
 *
 * Platform: M5Stack M5Cardputer with ESP32-S3 (240x135 display)
 * Framework: Arduino / PlatformIO
 */

#include <M5Cardputer.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <TJpg_Decoder.h>
#include <SPIFFS.h>

// ==================== COLOR PALETTE ====================
#define KTOX_RED      0xC02D2B
#define KTOX_DARK_RED 0x641410
#define KTOX_GREEN    0x1E8449
#define KTOX_YELLOW   0xD4AC0D
#define KTOX_WHITE    0xF5EDE8
#define KTOX_BLUE     0x1F618D

// ==================== GLOBALS ====================
WebSocketsClient webSocket;
bool ws_connected = false;
int frame_count = 0;
unsigned long last_connection_attempt = 0;
unsigned long last_frame_time = 0;

struct Settings {
    char wifi_ssid[64];
    char wifi_password[64];
    char ktox_host[64];
    uint16_t ktox_port;
    char auth_token[256];
} settings;

// ==================== JPEG DECODER CALLBACK ====================
static bool jpeg_decode_callback(int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t* bitmap) {
    // Copy decoded JPEG data to display buffer
    M5Cardputer.Display.pushImage(x, y, w, h, bitmap);
    return true;
}

// ==================== BASE64 DECODE ====================
static const char base64_chars[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

int base64_decode(const char* in, size_t in_len, uint8_t* out, size_t out_max) {
    size_t i = 0, j = 0;
    uint32_t v = 0;
    int bits = 0;

    for (i = 0; i < in_len && j < out_max; i++) {
        char c = in[i];
        if (c >= 'A' && c <= 'Z') v = (v << 6) | (c - 'A');
        else if (c >= 'a' && c <= 'z') v = (v << 6) | (26 + c - 'a');
        else if (c >= '0' && c <= '9') v = (v << 6) | (52 + c - '0');
        else if (c == '+') v = (v << 6) | 62;
        else if (c == '/') v = (v << 6) | 63;
        else if (c == '=') break;
        else continue;

        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            out[j++] = (v >> bits) & 0xFF;
        }
    }
    return j;
}

// ==================== SETTINGS MANAGEMENT ====================
void load_settings() {
    if (SPIFFS.exists("/settings.json")) {
        File file = SPIFFS.open("/settings.json", "r");
        if (file) {
            DynamicJsonDocument doc(512);
            deserializeJson(doc, file);

            strcpy(settings.wifi_ssid, doc["wifi_ssid"] | "");
            strcpy(settings.wifi_password, doc["wifi_password"] | "");
            strcpy(settings.ktox_host, doc["ktox_host"] | "192.168.1.100");
            settings.ktox_port = doc["ktox_port"] | 8765;
            strcpy(settings.auth_token, doc["auth_token"] | "");

            file.close();
            Serial.printf("Settings loaded: SSID=%s, Host=%s:%d\n",
                          settings.wifi_ssid, settings.ktox_host, settings.ktox_port);
        }
    } else {
        strcpy(settings.wifi_ssid, "");
        strcpy(settings.wifi_password, "");
        strcpy(settings.ktox_host, "192.168.1.100");
        settings.ktox_port = 8765;
        strcpy(settings.auth_token, "");
    }
}

void save_settings() {
    DynamicJsonDocument doc(512);
    doc["wifi_ssid"] = settings.wifi_ssid;
    doc["wifi_password"] = settings.wifi_password;
    doc["ktox_host"] = settings.ktox_host;
    doc["ktox_port"] = settings.ktox_port;
    doc["auth_token"] = settings.auth_token;

    File file = SPIFFS.open("/settings.json", "w");
    if (file) {
        serializeJson(doc, file);
        file.close();
        Serial.println("Settings saved");
    }
}

// ==================== SETUP ====================
void setup() {
    M5Cardputer.begin();
    Serial.begin(115200);
    delay(2000);

    Serial.println("\n\n================================");
    Serial.println("KTOx Remote Control");
    Serial.println("M5Cardputer Edition");
    Serial.println("================================");

    // Initialize display
    M5Cardputer.Display.fillScreen(TFT_BLACK);
    M5Cardputer.Display.setTextSize(2);
    M5Cardputer.Display.setTextColor(KTOX_RED, TFT_BLACK);
    M5Cardputer.Display.println("KTOx Remote");
    M5Cardputer.Display.setTextSize(1);
    M5Cardputer.Display.setTextColor(KTOX_WHITE);
    M5Cardputer.Display.println("Initializing...");

    // Initialize SPIFFS
    if (!SPIFFS.begin(true)) {
        M5Cardputer.Display.setTextColor(TFT_RED);
        M5Cardputer.Display.println("SPIFFS init failed!");
        while(1) delay(100);
    }

    // Setup JPEG decoder
    TJpgDec.setJpgScale(1);
    TJpgDec.setCallback(jpeg_decode_callback);

    // Load settings
    load_settings();

    // If no WiFi configured, show setup wizard
    if (strlen(settings.wifi_ssid) == 0) {
        show_setup_wizard();
    } else {
        setup_wifi();
    }

    delay(1000);
}

// ==================== SETUP WIZARD ====================
String get_string_input(const char* prompt, int max_len) {
    String result = "";
    M5Cardputer.Display.fillScreen(TFT_BLACK);
    M5Cardputer.Display.setTextColor(KTOX_YELLOW);
    M5Cardputer.Display.setTextSize(1);
    M5Cardputer.Display.setCursor(0, 0);
    M5Cardputer.Display.println(prompt);

    unsigned long timeout = millis() + 120000; // 2 minute timeout

    while (millis() < timeout) {
        M5Cardputer.update();

        if (M5Cardputer.Keyboard.isChange()) {
            auto status = M5Cardputer.Keyboard.keysState();

            if (status.enter) {
                return result;
            }
            if (status.del && result.length() > 0) {
                result.remove(result.length() - 1);
            }
            if (!status.word.empty() && result.length() < max_len) {
                result += String(status.word.c_str());
            }

            M5Cardputer.Display.fillRect(0, 30, 240, 80, TFT_BLACK);
            M5Cardputer.Display.setCursor(0, 30);
            M5Cardputer.Display.setTextColor(KTOX_WHITE);
            M5Cardputer.Display.print(result);
            M5Cardputer.Display.setTextColor(KTOX_YELLOW);
            M5Cardputer.Display.setCursor(0, 110);
            M5Cardputer.Display.println("ENTER:OK  DEL:Back");
        }
        delay(10);
    }
    return result;
}

void show_setup_wizard() {
    Serial.println("Starting setup wizard...");

    String ssid = get_string_input("WiFi SSID:", 63);
    if (ssid.length() == 0) return;
    strcpy(settings.wifi_ssid, ssid.c_str());

    String password = get_string_input("WiFi Password:", 63);
    strcpy(settings.wifi_password, password.c_str());

    String host = get_string_input("KTOX_Pi IP:", 63);
    if (host.length() == 0) host = "192.168.1.100";
    strcpy(settings.ktox_host, host.c_str());

    save_settings();
    setup_wifi();
}

// ==================== WiFi SETUP ====================
void setup_wifi() {
    M5Cardputer.Display.fillScreen(TFT_BLACK);
    M5Cardputer.Display.setTextColor(KTOX_YELLOW);
    M5Cardputer.Display.setTextSize(1);
    M5Cardputer.Display.setCursor(0, 0);
    M5Cardputer.Display.println("Connecting to WiFi...");

    Serial.printf("Connecting to WiFi: %s\n", settings.wifi_ssid);

    WiFi.mode(WIFI_STA);
    WiFi.begin(settings.wifi_ssid, settings.wifi_password);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        M5Cardputer.Display.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected!");
        Serial.printf("IP: %s\n", WiFi.localIP().toString().c_str());

        M5Cardputer.Display.setTextColor(KTOX_GREEN);
        M5Cardputer.Display.println("\nWiFi connected!");
        M5Cardputer.Display.setTextColor(KTOX_WHITE);
        M5Cardputer.Display.printf("IP: %s\n", WiFi.localIP().toString().c_str());

        delay(1000);
        setup_websocket();
    } else {
        Serial.println("\nWiFi connection failed!");
        M5Cardputer.Display.setTextColor(TFT_RED);
        M5Cardputer.Display.println("Connection failed!");
        delay(2000);
        show_setup_wizard();
    }
}

// ==================== WEBSOCKET SETUP ====================
void setup_websocket() {
    Serial.printf("Connecting to WebSocket: %s:%d\n", settings.ktox_host, settings.ktox_port);

    webSocket.begin(settings.ktox_host, settings.ktox_port, "/");
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(3000);

    M5Cardputer.Display.fillScreen(TFT_BLACK);
    M5Cardputer.Display.setTextColor(KTOX_YELLOW);
    M5Cardputer.Display.setTextSize(1);
    M5Cardputer.Display.println("Connecting to KTOX...");
}

// ==================== WEBSOCKET EVENT HANDLER ====================
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_DISCONNECTED:
            Serial.println("[WS] Disconnected");
            ws_connected = false;
            M5Cardputer.Display.fillScreen(TFT_BLACK);
            M5Cardputer.Display.setTextColor(KTOX_RED);
            M5Cardputer.Display.println("Disconnected");
            M5Cardputer.Display.println("Reconnecting...");
            break;

        case WStype_CONNECTED:
            Serial.println("[WS] Connected!");
            ws_connected = true;

            // If we have an auth token, send it immediately
            if (strlen(settings.auth_token) > 0) {
                DynamicJsonDocument doc(512);
                doc["type"] = "auth";
                doc["token"] = settings.auth_token;
                String json;
                serializeJson(doc, json);
                webSocket.sendTXT(json);
                Serial.println("[WS] Sent auth token");
            }

            M5Cardputer.Display.fillScreen(TFT_BLACK);
            M5Cardputer.Display.setTextColor(KTOX_GREEN);
            M5Cardputer.Display.println("Connected!");
            M5Cardputer.Display.setTextColor(KTOX_WHITE);
            M5Cardputer.Display.println("Waiting for frames...");
            break;

        case WStype_TEXT: {
            // Parse incoming JSON message
            DynamicJsonDocument doc(50000);
            DeserializationError error = deserializeJson(doc, payload);

            if (error) {
                Serial.printf("[WS] JSON error: %s\n", error.c_str());
                return;
            }

            const char* msg_type = doc["type"];
            if (!msg_type) return;

            // Handle frame_m5 messages (M5Cardputer-specific frames)
            if (strcmp(msg_type, "frame_m5") == 0) {
                const char* data = doc["data"];
                if (data) {
                    handle_frame(data);
                }
            }
            // Handle standard frame messages (for backward compatibility)
            else if (strcmp(msg_type, "frame") == 0) {
                const char* data = doc["data"];
                if (data) {
                    handle_frame(data);
                }
            }
            // Handle auth responses
            else if (strcmp(msg_type, "auth_ok") == 0) {
                Serial.println("[WS] Authentication successful");
            }
            else if (strcmp(msg_type, "auth_error") == 0) {
                Serial.println("[WS] Authentication failed");
                ws_connected = false;
                webSocket.disconnect();
            }
            break;
        }

        case WStype_BIN:
            Serial.printf("[WS] Binary data received (%d bytes)\n", length);
            break;

        case WStype_ERROR:
            Serial.println("[WS] Error occurred");
            break;

        case WStype_FRAGMENT_TEXT_START:
        case WStype_FRAGMENT_BIN_START:
        case WStype_FRAGMENT:
        case WStype_FRAGMENT_FIN:
            break;
    }
}

// ==================== FRAME HANDLER ====================
void handle_frame(const char* base64_data) {
    if (!base64_data) return;

    size_t b64_len = strlen(base64_data);
    size_t max_jpeg_size = b64_len / 4 * 3 + 10;

    // Allocate buffer for decoded JPEG
    uint8_t* jpeg_buffer = (uint8_t*)malloc(max_jpeg_size);
    if (!jpeg_buffer) {
        Serial.println("[FRAME] Failed to allocate JPEG buffer");
        return;
    }

    // Decode base64
    int jpeg_len = base64_decode(base64_data, b64_len, jpeg_buffer, max_jpeg_size);
    if (jpeg_len <= 0) {
        Serial.println("[FRAME] Base64 decode failed");
        free(jpeg_buffer);
        return;
    }

    Serial.printf("[FRAME] Decoded %d bytes from base64\n", jpeg_len);

    // Draw JPEG
    if (TJpgDec.drawJpg(0, 0, jpeg_buffer, jpeg_len) == 0) {
        frame_count++;
        last_frame_time = millis();
        Serial.printf("[FRAME] Frame displayed (#%d)\n", frame_count);
    } else {
        Serial.println("[FRAME] JPEG decode failed");
    }

    free(jpeg_buffer);

    // Draw status bar
    draw_status_bar();
}

// ==================== STATUS BAR ====================
void draw_status_bar() {
    // Draw connection status and frame count at bottom
    M5Cardputer.Display.setTextSize(1);
    M5Cardputer.Display.setTextColor(ws_connected ? KTOX_GREEN : KTOX_RED, TFT_BLACK);
    M5Cardputer.Display.fillRect(0, 130, 240, 5, TFT_BLACK);

    char status[64];
    unsigned long uptime_sec = millis() / 1000;
    unsigned long fps = frame_count > 0 ? (frame_count * 1000 / (millis() + 1)) : 0;

    snprintf(status, sizeof(status), "[%s] %d frames | %lds",
             ws_connected ? "●" : "○",
             frame_count,
             uptime_sec);

    M5Cardputer.Display.setCursor(0, 132);
    M5Cardputer.Display.print(status);
}

// ==================== INPUT HANDLING ====================
void send_button(const char* button_name, const char* state) {
    if (!ws_connected) return;

    DynamicJsonDocument doc(256);
    doc["type"] = "input";
    doc["button"] = button_name;
    doc["state"] = state;

    String json;
    serializeJson(doc, json);
    webSocket.sendTXT(json);

    Serial.printf("[INPUT] Sent %s %s\n", button_name, state);
}

void handle_keyboard_input() {
    M5Cardputer.update();

    if (M5Cardputer.Keyboard.isChange()) {
        auto status = M5Cardputer.Keyboard.keysState();

        // Arrow key / WASD navigation
        if (status.up || status.word.find("w") != std::string::npos || status.word.find("i") != std::string::npos) {
            send_button("UP", "press");
            delay(100);
            send_button("UP", "release");
        }
        if (status.down || status.word.find("s") != std::string::npos || status.word.find("k") != std::string::npos) {
            send_button("DOWN", "press");
            delay(100);
            send_button("DOWN", "release");
        }
        if (status.left || status.word.find("a") != std::string::npos || status.word.find("j") != std::string::npos) {
            send_button("LEFT", "press");
            delay(100);
            send_button("LEFT", "release");
        }
        if (status.right || status.word.find("d") != std::string::npos || status.word.find("l") != std::string::npos) {
            send_button("RIGHT", "press");
            delay(100);
            send_button("RIGHT", "release");
        }

        // Enter/Space for OK
        if (status.enter || status.word.find(" ") != std::string::npos) {
            send_button("OK", "press");
            delay(100);
            send_button("OK", "release");
        }

        // Settings menu
        if (status.word.find("h") != std::string::npos || status.word.find("H") != std::string::npos) {
            show_settings_menu();
        }
    }
}

void show_settings_menu() {
    M5Cardputer.Display.fillScreen(TFT_BLACK);
    M5Cardputer.Display.setTextColor(KTOX_YELLOW);
    M5Cardputer.Display.setTextSize(1);
    M5Cardputer.Display.setCursor(0, 0);
    M5Cardputer.Display.println("Settings");
    M5Cardputer.Display.println("");
    M5Cardputer.Display.setTextColor(KTOX_WHITE);
    M5Cardputer.Display.println("Press R to reconfigure WiFi");
    M5Cardputer.Display.println("Press S to save current");
    M5Cardputer.Display.println("Press ENTER to go back");

    while (true) {
        M5Cardputer.update();
        if (M5Cardputer.Keyboard.isChange()) {
            auto status = M5Cardputer.Keyboard.keysState();

            if (status.word.find("r") != std::string::npos || status.word.find("R") != std::string::npos) {
                show_setup_wizard();
                return;
            }
            if (status.word.find("s") != std::string::npos || status.word.find("S") != std::string::npos) {
                save_settings();
                M5Cardputer.Display.println("Saved!");
                delay(1000);
                return;
            }
            if (status.enter) {
                return;
            }
        }
        delay(10);
    }
}

// ==================== MAIN LOOP ====================
void loop() {
    webSocket.loop();
    handle_keyboard_input();

    // Attempt reconnection if needed
    if (!ws_connected && (millis() - last_connection_attempt > 5000)) {
        last_connection_attempt = millis();
        Serial.println("[MAIN] Attempting to reconnect...");
        setup_websocket();
    }

    delay(10);
}
