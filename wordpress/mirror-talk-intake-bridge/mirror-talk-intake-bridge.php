<?php
/**
 * Plugin Name: Mirror Talk Intake Bridge
 * Description: Sends Contact Form 7 guest applications to the Python intake API.
 * Version: 0.1.0
 * Author: Mirror Talk
 */

if (!defined('ABSPATH')) {
    exit;
}

add_action('wpcf7_mail_sent', 'mirror_talk_send_guest_intake_to_api');

function mirror_talk_send_guest_intake_to_api($contact_form) {
    if (!$contact_form instanceof WPCF7_ContactForm) {
        return;
    }

    /*
     * Replace this with your actual Contact Form 7 form ID.
     * You can find it in the WordPress admin.
     */
    $target_form_id = 6485687;

    if ((int) $contact_form->id() !== $target_form_id) {
        return;
    }

    $submission = WPCF7_Submission::get_instance();
    if (!$submission) {
        return;
    }

    $posted_data = $submission->get_posted_data();

    $payload = [
        'full_name' => sanitize_text_field($posted_data['full_name'] ?? ''),
        'email' => sanitize_email($posted_data['email'] ?? ''),
        'website' => esc_url_raw($posted_data['website'] ?? ''),
        'social_handles' => sanitize_text_field($posted_data['social_handles'] ?? ''),
        'background' => sanitize_textarea_field($posted_data['background'] ?? ''),
        'profession' => sanitize_textarea_field($posted_data['profession'] ?? ''),
        'passionate_topics' => sanitize_textarea_field($posted_data['passionate_topics'] ?? ''),
        'message' => sanitize_textarea_field($posted_data['message'] ?? ''),
        'experience' => sanitize_textarea_field($posted_data['experience'] ?? ''),
        'additional_info' => sanitize_textarea_field($posted_data['additional_info'] ?? ''),
        'has_social_media' => sanitize_text_field($posted_data['has_social_media'] ?? ''),
    ];

    /*
     * Replace with your deployed backend endpoint.
     */
    $endpoint = 'https://ask-mirror-talk-production.up.railway.app/api/intake';

    /*
     * Optional shared secret. If you use it in Python later,
     * replace this value and validate it server-side.
     */
    $api_token = 'replace-with-a-secret-token';

    $response = wp_remote_post($endpoint, [
        'method'  => 'POST',
        'timeout' => 20,
        'headers' => [
            'Content-Type' => 'application/json',
            'Accept' => 'application/json',
            'X-Api-Token' => $api_token,
        ],
        'body' => wp_json_encode($payload),
    ]);

    if (is_wp_error($response)) {
        error_log('Mirror Talk Intake Bridge error: ' . $response->get_error_message());
        return;
    }

    $status_code = wp_remote_retrieve_response_code($response);

    if ($status_code < 200 || $status_code >= 300) {
        error_log('Mirror Talk Intake Bridge unexpected response code: ' . $status_code);
        error_log('Mirror Talk Intake Bridge response body: ' . wp_remote_retrieve_body($response));
    }
}
