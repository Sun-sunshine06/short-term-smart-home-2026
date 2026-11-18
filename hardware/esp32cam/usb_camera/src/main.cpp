#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <esp_camera.h>
#include "ap_config.h"

WebServer server(80);
bool cameraReady = false;
unsigned long framesCaptured = 0;

void captureFrame(bool usb) {
    camera_fb_t *frame = cameraReady ? esp_camera_fb_get() : nullptr;
    if (!frame) {
        if (usb) Serial.println("CAPTURE_FAILED");
        else server.send(503, "text/plain", "CAPTURE_FAILED");
        return;
    }
    ++framesCaptured;
    if (usb) {
        Serial.printf("JPEG %u\n", static_cast<unsigned>(frame->len));
        Serial.write(frame->buf, frame->len);
        Serial.flush();
    } else {
        server.sendHeader("Cache-Control", "no-store");
        server.setContentLength(frame->len);
        server.send(200, "image/jpeg", "");
        server.sendContent(reinterpret_cast<const char*>(frame->buf), frame->len);
    }
    esp_camera_fb_return(frame);
}

void setup() {
    Serial.begin(921600);
    camera_config_t c{};
    // Espressif CameraWebServer pin map for CAMERA_MODEL_AI_THINKER.
    c.pin_pwdn = 32; c.pin_reset = -1; c.pin_xclk = 0;
    c.pin_sscb_sda = 26; c.pin_sscb_scl = 27;
    c.pin_d0 = 5; c.pin_d1 = 18; c.pin_d2 = 19; c.pin_d3 = 21;
    c.pin_d4 = 36; c.pin_d5 = 39; c.pin_d6 = 34; c.pin_d7 = 35;
    c.pin_vsync = 25; c.pin_href = 23; c.pin_pclk = 22;
    c.ledc_channel = LEDC_CHANNEL_0;
    c.ledc_timer = LEDC_TIMER_0;
    c.xclk_freq_hz = 20000000;
    c.pixel_format = PIXFORMAT_JPEG;
    c.frame_size = FRAMESIZE_VGA;
    c.jpeg_quality = 12;
    c.fb_count = psramFound() ? 2 : 1;
    c.grab_mode = CAMERA_GRAB_LATEST;
    c.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
    auto err = esp_camera_init(&c);
    cameraReady = err == ESP_OK;
    Serial.printf("CAMERA_%s,ERR_CODE:0x%04x\n", cameraReady ? "OK" : "ERR", err);
    if (cameraReady) {
        auto *s = esp_camera_sensor_get();
        Serial.printf("SENSOR_PID:0x%04x\n", s->id.PID);
        if (s->id.PID == OV3660_PID) {
            s->set_vflip(s, 1);
            s->set_brightness(s, 1);
            s->set_saturation(s, -2);
        }
    }
    WiFi.persistent(false);
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAP("SmartHomeCam", apPassword)) {
        Serial.println("AP_FAILED");
        return;
    }
    Serial.println("AP_IP:" + WiFi.softAPIP().toString());
    server.on("/", []() {server.send(200, "text/html", "<meta name='viewport' content='width=device-width'><title>SmartHomeCam</title><img style='max-width:100%' src='/capture'><p><a href='/'>Refresh photo</a></p>");});
    server.on("/status", []() {
        server.send(200, "application/json", String("{\"camera_ready\":") + (cameraReady ? "true" : "false") + ",\"capture_count\":" + framesCaptured + "}");
    });
    server.on("/capture", [](){captureFrame(false);});
    server.begin();
    Serial.println("HTTP_READY");
}

void loop() {
    server.handleClient();
    static char command[16]{};
    static size_t used = 0;
    while (Serial.available()) {
        char ch = Serial.read();
        if (ch == '\n') {
            command[used] = '\0';
            if (strcmp(command, "CAPTURE") == 0) captureFrame(true);
            used = 0;
        } else if (ch != '\r' && used < sizeof(command)-1) command[used++] = ch;
    }
    delay(1);
}
