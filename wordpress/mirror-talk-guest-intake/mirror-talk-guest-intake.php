<?php
/**
 * Plugin Name: Mirror Talk Guest Intake
 * Plugin URI: https://www.mirrortalkpodcast.com/
 * Description: Adds a shortcode for embedding the Mirror Talk guest intake experience from the intake application.
 * Version: 0.1.0
 * Author: Mirror Talk
 * Author URI: https://www.mirrortalkpodcast.com/
 * License: GPL2+
 * Text Domain: mirror-talk-guest-intake
 */

if (!defined('ABSPATH')) {
    exit;
}

final class MirrorTalkGuestIntakePlugin
{
    private const OPTION_GROUP = 'mirror_talk_guest_intake_options';
    private const OPTION_NAME = 'mirror_talk_guest_intake_settings';
    private const SHORTCODE = 'mirror_talk_guest_intake';
    private const DEFAULT_API_URL = 'https://apply.mirrortalkpodcast.com/api/intake';

    public function __construct()
    {
        add_action('init', [$this, 'register_shortcode']);
        add_action('wp_enqueue_scripts', [$this, 'register_assets']);
        add_action('admin_menu', [$this, 'register_settings_page']);
        add_action('admin_init', [$this, 'register_settings']);
    }

    public function register_shortcode(): void
    {
        add_shortcode(self::SHORTCODE, [$this, 'render_shortcode']);
    }

    public function register_assets(): void
    {
        wp_register_style(
            'mirror-talk-guest-intake',
            plugin_dir_url(__FILE__) . 'assets/css/mirror-talk-guest-intake.css',
            [],
            '0.1.0'
        );

        wp_register_script(
            'mirror-talk-guest-intake',
            plugin_dir_url(__FILE__) . 'assets/js/mirror-talk-guest-intake.js',
            [],
            '0.1.0',
            true
        );
    }

    public function register_settings_page(): void
    {
        add_options_page(
            __('Mirror Talk Guest Intake', 'mirror-talk-guest-intake'),
            __('Mirror Talk Intake', 'mirror-talk-guest-intake'),
            'manage_options',
            'mirror-talk-guest-intake',
            [$this, 'render_settings_page']
        );
    }

    public function register_settings(): void
    {
        register_setting(
            self::OPTION_GROUP,
            self::OPTION_NAME,
            [$this, 'sanitize_settings']
        );

        add_settings_section(
            'mirror_talk_guest_intake_main',
            __('Intake Embed Settings', 'mirror-talk-guest-intake'),
            function () {
                echo '<p>' . esc_html__('Configure where the guest intake application is hosted and how it appears on the page.', 'mirror-talk-guest-intake') . '</p>';
            },
            'mirror-talk-guest-intake'
        );

        add_settings_field(
            'api_url',
            __('Intake API URL', 'mirror-talk-guest-intake'),
            [$this, 'render_text_field'],
            'mirror-talk-guest-intake',
            'mirror_talk_guest_intake_main',
            [
                'label_for' => 'mirror_talk_guest_intake_api_url',
                'name' => 'api_url',
                'placeholder' => self::DEFAULT_API_URL,
                'description' => __('The intake submission endpoint, for example https://apply.mirrortalkpodcast.com/api/intake', 'mirror-talk-guest-intake'),
            ]
        );

    }

    public function sanitize_settings(array $input): array
    {
        return [
            'api_url' => esc_url_raw($input['api_url'] ?? self::DEFAULT_API_URL),
        ];
    }

    public function render_settings_page(): void
    {
        if (!current_user_can('manage_options')) {
            return;
        }

        ?>
        <div class="wrap">
            <h1><?php esc_html_e('Mirror Talk Guest Intake', 'mirror-talk-guest-intake'); ?></h1>
            <form action="options.php" method="post">
                <?php
                settings_fields(self::OPTION_GROUP);
                do_settings_sections('mirror-talk-guest-intake');
                submit_button(__('Save Settings', 'mirror-talk-guest-intake'));
                ?>
            </form>
            <hr />
            <p><strong><?php esc_html_e('Shortcode:', 'mirror-talk-guest-intake'); ?></strong> <code>[mirror_talk_guest_intake]</code></p>
            <p><strong><?php esc_html_e('Example:', 'mirror-talk-guest-intake'); ?></strong> <code>[mirror_talk_guest_intake title="Be Our Next Guest"]</code></p>
        </div>
        <?php
    }

    public function render_text_field(array $args): void
    {
        $settings = $this->get_settings();
        $value = $settings[$args['name']] ?? '';

        printf(
            '<input type="url" class="regular-text" id="%1$s" name="%2$s[%3$s]" value="%4$s" placeholder="%5$s" />',
            esc_attr($args['label_for']),
            esc_attr(self::OPTION_NAME),
            esc_attr($args['name']),
            esc_attr($value),
            esc_attr($args['placeholder'])
        );

        if (!empty($args['description'])) {
            printf('<p class="description">%s</p>', esc_html($args['description']));
        }
    }

    public function render_shortcode(array $atts = []): string
    {
        $settings = $this->get_settings();
        $defaults = [
            'title' => __('Apply to Be a Guest', 'mirror-talk-guest-intake'),
            'subtitle' => __('Share your story with Mirror Talk through a short, guided guest application.', 'mirror-talk-guest-intake'),
            'api_url' => $settings['api_url'] ?? self::DEFAULT_API_URL,
        ];

        $atts = shortcode_atts($defaults, $atts, self::SHORTCODE);
        $api_url = esc_url($atts['api_url']);

        if (empty($api_url)) {
            return '<div class="mirror-talk-intake-error">' . esc_html__('Mirror Talk intake API URL is not configured yet.', 'mirror-talk-guest-intake') . '</div>';
        }

        wp_enqueue_style('mirror-talk-guest-intake');
        wp_enqueue_script('mirror-talk-guest-intake');

        ob_start();
        ?>
        <section
            class="mirror-talk-intake-wrapper"
        >
            <div class="mirror-talk-intake-card">
                <aside class="mirror-talk-intake-sidebar">
                    <p class="mirror-talk-intake-eyebrow"><?php esc_html_e('Mirror Talk Podcast', 'mirror-talk-guest-intake'); ?></p>
                    <h2 class="mirror-talk-intake-title"><?php echo esc_html($atts['title']); ?></h2>
                    <p class="mirror-talk-intake-subtitle"><?php echo esc_html($atts['subtitle']); ?></p>
                    <ol class="mirror-talk-intake-step-list">
                        <li class="mirror-talk-intake-step-indicator is-active" data-step-indicator><?php esc_html_e('Contact', 'mirror-talk-guest-intake'); ?></li>
                        <li class="mirror-talk-intake-step-indicator" data-step-indicator><?php esc_html_e('Story', 'mirror-talk-guest-intake'); ?></li>
                        <li class="mirror-talk-intake-step-indicator" data-step-indicator><?php esc_html_e('Fit', 'mirror-talk-guest-intake'); ?></li>
                    </ol>
                </aside>
                <div class="mirror-talk-intake-main">
                    <form class="mirror-talk-intake-form" data-mirror-talk-intake-form data-endpoint="<?php echo esc_url($api_url); ?>">
                        <section class="mirror-talk-intake-step is-active">
                            <h3><?php esc_html_e('Let’s start with the essentials.', 'mirror-talk-guest-intake'); ?></h3>
                            <p class="mirror-talk-intake-step-copy"><?php esc_html_e('Tell us who you are and how our team can reach you.', 'mirror-talk-guest-intake'); ?></p>

                            <label class="mirror-talk-intake-field">
                                <span><?php esc_html_e('Full Name', 'mirror-talk-guest-intake'); ?></span>
                                <input type="text" name="full_name" required />
                            </label>
                            <label class="mirror-talk-intake-field">
                                <span><?php esc_html_e('Email Address', 'mirror-talk-guest-intake'); ?></span>
                                <input type="email" name="email" required />
                            </label>
                            <label class="mirror-talk-intake-field">
                                <span><?php esc_html_e('Website', 'mirror-talk-guest-intake'); ?></span>
                                <input type="url" name="website" />
                            </label>
                            <label class="mirror-talk-intake-field">
                                <span><?php esc_html_e('Social Media Handles', 'mirror-talk-guest-intake'); ?></span>
                                <input type="text" name="social_handles" />
                            </label>
                        </section>

                        <section class="mirror-talk-intake-step">
                            <h3><?php esc_html_e('Tell us about your journey.', 'mirror-talk-guest-intake'); ?></h3>
                            <p class="mirror-talk-intake-step-copy"><?php esc_html_e('We want a concise sense of your story and perspective.', 'mirror-talk-guest-intake'); ?></p>

                            <label class="mirror-talk-intake-field is-full">
                                <span><?php esc_html_e('A brief overview of your personal and professional background', 'mirror-talk-guest-intake'); ?></span>
                                <textarea name="background" rows="5" required></textarea>
                            </label>
                            <label class="mirror-talk-intake-field is-full">
                                <span><?php esc_html_e('What is your current profession, and what led you to this career path?', 'mirror-talk-guest-intake'); ?></span>
                                <textarea name="profession" rows="4" required></textarea>
                            </label>
                            <label class="mirror-talk-intake-field is-full">
                                <span><?php esc_html_e('What topics or themes are you most passionate about discussing?', 'mirror-talk-guest-intake'); ?></span>
                                <textarea name="passionate_topics" rows="4" required></textarea>
                            </label>
                        </section>

                        <section class="mirror-talk-intake-step">
                            <h3><?php esc_html_e('Help us understand the fit.', 'mirror-talk-guest-intake'); ?></h3>
                            <p class="mirror-talk-intake-step-copy"><?php esc_html_e('These final answers help us decide whether your application is a strong match for an episode.', 'mirror-talk-guest-intake'); ?></p>

                            <label class="mirror-talk-intake-field is-full">
                                <span><?php esc_html_e('What message or takeaway would you like to leave with our listeners?', 'mirror-talk-guest-intake'); ?></span>
                                <textarea name="message" rows="4" required></textarea>
                            </label>
                            <label class="mirror-talk-intake-field is-full">
                                <span><?php esc_html_e('Have you been a guest on podcasts or spoken at events before?', 'mirror-talk-guest-intake'); ?></span>
                                <textarea name="experience" rows="3"></textarea>
                            </label>
                            <label class="mirror-talk-intake-field is-full">
                                <span><?php esc_html_e('Is there anything else you’d like us to know about you?', 'mirror-talk-guest-intake'); ?></span>
                                <textarea name="additional_info" rows="4"></textarea>
                            </label>
                            <label class="mirror-talk-intake-field is-full">
                                <span><?php esc_html_e('Are you following us on podcast platforms and social media?', 'mirror-talk-guest-intake'); ?></span>
                                <select name="has_social_media">
                                    <option value=""><?php esc_html_e('Prefer not to say', 'mirror-talk-guest-intake'); ?></option>
                                    <option value="Yes"><?php esc_html_e('Yes', 'mirror-talk-guest-intake'); ?></option>
                                    <option value="No"><?php esc_html_e('Not yet', 'mirror-talk-guest-intake'); ?></option>
                                </select>
                            </label>
                        </section>

                        <div class="mirror-talk-intake-actions">
                            <button type="button" class="mirror-talk-intake-button is-secondary" data-action="back"><?php esc_html_e('Back', 'mirror-talk-guest-intake'); ?></button>
                            <div class="mirror-talk-intake-actions-right">
                                <span class="mirror-talk-intake-counter" data-step-counter><?php esc_html_e('Step 1 of 3', 'mirror-talk-guest-intake'); ?></span>
                                <button type="button" class="mirror-talk-intake-button is-primary" data-action="next"><?php esc_html_e('Continue', 'mirror-talk-guest-intake'); ?></button>
                                <button type="submit" class="mirror-talk-intake-button is-primary" data-action="submit" hidden><?php esc_html_e('Submit Application', 'mirror-talk-guest-intake'); ?></button>
                            </div>
                        </div>
                        <p class="mirror-talk-intake-message" data-intake-message aria-live="polite"></p>
                    </form>
                </div>
            </div>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    private function get_settings(): array
    {
        $settings = get_option(self::OPTION_NAME, []);

        return [
            'api_url' => $settings['api_url'] ?? self::DEFAULT_API_URL,
        ];
    }
}

new MirrorTalkGuestIntakePlugin();
