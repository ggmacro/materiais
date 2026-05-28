/*
 * esp32_csi_udp_main.c
 *
 * Firmware ESP-IDF para ESP32/ESP32-S3:
 * - conecta no Wi-Fi
 * - liga CSI
 * - envia frames CSI por UDP para o PC rodando testewifi.py
 *
 * Coloque este arquivo em:
 *     seu_projeto_esp_idf/main/main.c
 *
 * Ajuste WIFI_SSID, WIFI_PASS e TARGET_IP antes de compilar.
 *
 * No ESP-IDF menuconfig, habilite:
 *     Component config -> Wi-Fi -> Wi-Fi CSI (Channel State Information)
 */

#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include <arpa/inet.h>
#include <sys/socket.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#define WIFI_SSID "SUA_REDE_WIFI"
#define WIFI_PASS "SUA_SENHA_WIFI"
#define TARGET_IP "192.168.1.20"
#define TARGET_PORT 5006

#define CSI_MAX_LEN 612
#define WIFI_CONNECTED_BIT BIT0

static const char *TAG = "csi_udp";
static EventGroupHandle_t s_wifi_event_group;
static QueueHandle_t s_csi_queue;

typedef struct {
    int64_t ts_us;
    int8_t rssi;
    uint16_t len;
    int8_t buf[CSI_MAX_LEN];
} csi_packet_t;

static void wifi_event_handler(
    void *arg,
    esp_event_base_t event_base,
    int32_t event_id,
    void *event_data
) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        esp_wifi_connect();
        ESP_LOGW(TAG, "Wi-Fi desconectado, tentando reconectar");
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "IP obtido: " IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void wifi_csi_rx_cb(void *ctx, wifi_csi_info_t *info) {
    if (!info || !info->buf || info->len == 0) {
        return;
    }

    csi_packet_t packet = {0};
    packet.ts_us = esp_timer_get_time();
    packet.rssi = info->rx_ctrl.rssi;
    packet.len = info->len > CSI_MAX_LEN ? CSI_MAX_LEN : info->len;
    memcpy(packet.buf, info->buf, packet.len);

    xQueueSend(s_csi_queue, &packet, 0);
}

static void wifi_init_sta(void) {
    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT,
        ESP_EVENT_ANY_ID,
        &wifi_event_handler,
        NULL,
        NULL
    ));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT,
        IP_EVENT_STA_GOT_IP,
        &wifi_event_handler,
        NULL,
        NULL
    ));

    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.sta.ssid, WIFI_SSID, sizeof(wifi_config.sta.ssid));
    strncpy((char *)wifi_config.sta.password, WIFI_PASS, sizeof(wifi_config.sta.password));
    wifi_config.sta.threshold.authmode = WIFI_AUTH_OPEN;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
}

static void csi_init(void) {
    wifi_csi_config_t csi_config = {
        .lltf_en = true,
        .htltf_en = true,
        .stbc_htltf2_en = true,
        .ltf_merge_en = true,
        .channel_filter_en = false,
        .manu_scale = false,
        .shift = 0,
        .dump_ack_en = false,
    };

    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_rx_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
    ESP_LOGI(TAG, "CSI ativado");
}

static void udp_sender_task(void *param) {
    struct sockaddr_in dest_addr = {0};
    dest_addr.sin_addr.s_addr = inet_addr(TARGET_IP);
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(TARGET_PORT);

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "Falha ao criar socket UDP");
        vTaskDelete(NULL);
        return;
    }

    char payload[4096];
    csi_packet_t packet;

    while (true) {
        if (xQueueReceive(s_csi_queue, &packet, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        int offset = snprintf(
            payload,
            sizeof(payload),
            "{\"type\":\"csi\",\"ts_us\":%lld,\"rssi\":%d,\"len\":%u,\"csi\":[",
            (long long)packet.ts_us,
            packet.rssi,
            packet.len
        );

        for (int i = 0; i < packet.len && offset < (int)sizeof(payload) - 8; i++) {
            offset += snprintf(
                payload + offset,
                sizeof(payload) - offset,
                "%d%s",
                packet.buf[i],
                i == packet.len - 1 ? "" : ","
            );
        }

        snprintf(payload + offset, sizeof(payload) - offset, "]}");
        sendto(sock, payload, strlen(payload), 0, (struct sockaddr *)&dest_addr, sizeof(dest_addr));
    }
}

void app_main(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    } else {
        ESP_ERROR_CHECK(ret);
    }

    s_csi_queue = xQueueCreate(16, sizeof(csi_packet_t));
    if (!s_csi_queue) {
        ESP_LOGE(TAG, "Falha ao criar fila CSI");
        return;
    }

    wifi_init_sta();
    xEventGroupWaitBits(s_wifi_event_group, WIFI_CONNECTED_BIT, false, true, portMAX_DELAY);
    csi_init();

    xTaskCreate(udp_sender_task, "udp_sender_task", 8192, NULL, 5, NULL);
}
