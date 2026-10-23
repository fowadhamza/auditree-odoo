<?php
/**
 * Plugin Name: Auditree Odoo Recruitment
 * Description: Lists Odoo's published vacancies on auditree.com and posts job
 *              applications into Odoo recruitment.
 * Version:     1.0.0
 * Author:      Auditree
 * License:     LGPL-3.0-or-later
 *
 * NOT YET TESTED against a live WordPress install. Verify on staging first.
 *
 * Configuration -- put these in wp-config.php, NOT in the database and NOT in
 * this file, so the token never lands in a database export or in git:
 *
 *     define( 'AUDITREE_ODOO_URL',   'https://odoo.auditree.com' );
 *     define( 'AUDITREE_ODOO_TOKEN', '...' );  // Odoo: Settings > Technical >
 *                                              // System Parameters >
 *                                              // xn_recruitment_bridge.api_token
 *
 * Shortcodes:
 *     [auditree_jobs]              list open vacancies, each linking to a form
 *     [auditree_apply job_id="1"]  the application form for one vacancy
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

const AUDITREE_JOBS_TRANSIENT = 'auditree_odoo_jobs';
const AUDITREE_JOBS_TTL       = 15 * MINUTE_IN_SECONDS;

/**
 * Fetch published vacancies from Odoo.
 *
 * Cached, because a careers page should not make an outbound HTTP call on
 * every pageview, and should not go blank the moment Odoo restarts. On a
 * failed fetch the previous list is served stale rather than showing an error
 * to a candidate.
 *
 * @return array[] List of job arrays, possibly empty.
 */
function auditree_get_jobs() {
	$cached = get_transient( AUDITREE_JOBS_TRANSIENT );
	if ( false !== $cached ) {
		return $cached;
	}

	$response = wp_remote_get(
		AUDITREE_ODOO_URL . '/auditree/recruitment/jobs',
		array( 'timeout' => 10 )
	);

	if ( is_wp_error( $response ) || 200 !== wp_remote_retrieve_response_code( $response ) ) {
		// Keep whatever we last had rather than showing an empty careers page.
		$stale = get_option( AUDITREE_JOBS_TRANSIENT . '_stale', array() );
		set_transient( AUDITREE_JOBS_TRANSIENT, $stale, MINUTE_IN_SECONDS );
		return $stale;
	}

	$body = json_decode( wp_remote_retrieve_body( $response ), true );
	$jobs = isset( $body['jobs'] ) && is_array( $body['jobs'] ) ? $body['jobs'] : array();

	set_transient( AUDITREE_JOBS_TRANSIENT, $jobs, AUDITREE_JOBS_TTL );
	update_option( AUDITREE_JOBS_TRANSIENT . '_stale', $jobs, false );

	return $jobs;
}

/**
 * [auditree_jobs] -- the careers list.
 */
function auditree_jobs_shortcode( $atts ) {
	$atts = shortcode_atts( array( 'apply_page' => '/apply' ), $atts, 'auditree_jobs' );
	$jobs = auditree_get_jobs();

	if ( empty( $jobs ) ) {
		return '<p class="auditree-jobs-empty">' .
			esc_html__( 'There are no open positions at the moment.', 'auditree' ) .
			'</p>';
	}

	$out = '<ul class="auditree-jobs">';
	foreach ( $jobs as $job ) {
		$url = add_query_arg( 'job_id', (int) $job['id'], $atts['apply_page'] );

		$out .= '<li class="auditree-job">';
		$out .= '<h3><a href="' . esc_url( $url ) . '">' . esc_html( $job['name'] ) . '</a></h3>';

		$meta = array_filter( array( $job['department'], $job['location'], $job['country'] ) );
		if ( $meta ) {
			$out .= '<p class="auditree-job-meta">' . esc_html( implode( ' - ', $meta ) ) . '</p>';
		}

		// Odoo's job description is authored in Odoo's own HTML editor, so it
		// is trusted content from our own backend -- but it still goes through
		// wp_kses_post rather than being echoed raw.
		$out .= '<div class="auditree-job-description">' .
			wp_kses_post( $job['description_html'] ) . '</div>';
		$out .= '</li>';
	}
	$out .= '</ul>';

	return $out;
}
add_shortcode( 'auditree_jobs', 'auditree_jobs_shortcode' );

/**
 * [auditree_apply job_id="1"] -- the application form.
 *
 * Deliberately a plain HTML form rather than a form-plugin integration, so it
 * works on any WordPress install. If auditree.com standardises on a form
 * plugin, replace this with that plugin's submission hook and keep
 * auditree_submit_application() below unchanged.
 */
function auditree_apply_shortcode( $atts ) {
	$atts = shortcode_atts( array( 'job_id' => '' ), $atts, 'auditree_apply' );

	$job_id = $atts['job_id'] ? (int) $atts['job_id'] : (int) ( $_GET['job_id'] ?? 0 );
	if ( ! $job_id ) {
		return '<p>' . esc_html__( 'No position selected.', 'auditree' ) . '</p>';
	}

	// Only offer a form for a job Odoo actually published. Without this the
	// page would happily post an arbitrary id and show the candidate an error.
	$jobs  = auditree_get_jobs();
	$match = null;
	foreach ( $jobs as $job ) {
		if ( (int) $job['id'] === $job_id ) {
			$match = $job;
			break;
		}
	}
	if ( ! $match ) {
		return '<p>' . esc_html__( 'That position is no longer open.', 'auditree' ) . '</p>';
	}

	$notice = '';
	$status = sanitize_key( $_GET['auditree_status'] ?? '' );
	if ( 'ok' === $status ) {
		$notice = '<p class="auditree-notice auditree-ok">' .
			esc_html__( 'Thank you -- your application has been received.', 'auditree' ) . '</p>';
	} elseif ( 'duplicate' === $status ) {
		$notice = '<p class="auditree-notice auditree-ok">' .
			esc_html__( 'You have already applied for this position.', 'auditree' ) . '</p>';
	} elseif ( $status ) {
		$notice = '<p class="auditree-notice auditree-error">' .
			esc_html__( 'Sorry, your application could not be submitted. Please try again.', 'auditree' ) .
			'</p>';
	}

	ob_start();
	?>
	<?php echo $notice; // phpcs:ignore -- built from esc_html above ?>
	<form class="auditree-apply" method="post" enctype="multipart/form-data"
		action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
		<input type="hidden" name="action" value="auditree_apply">
		<input type="hidden" name="job_id" value="<?php echo esc_attr( $job_id ); ?>">
		<input type="hidden" name="redirect_to" value="<?php echo esc_url( get_permalink() ); ?>">
		<?php wp_nonce_field( 'auditree_apply_' . $job_id, 'auditree_nonce' ); ?>

		<p><strong><?php echo esc_html( $match['name'] ); ?></strong></p>

		<p><label>Name<br><input type="text" name="name" required maxlength="200"></label></p>
		<p><label>Email<br><input type="email" name="email" required maxlength="128"></label></p>
		<p><label>Phone<br><input type="text" name="phone" maxlength="32"></label></p>
		<p><label>LinkedIn<br><input type="url" name="linkedin" maxlength="200"></label></p>
		<p><label>Cover letter<br><textarea name="letter" rows="6" maxlength="20000"></textarea></label></p>
		<p><label>CV<br><input type="file" name="cv" accept=".pdf,.doc,.docx,.odt,.rtf,.txt"></label></p>

		<!-- Honeypot. A real candidate never fills this in; bots fill everything. -->
		<p style="position:absolute;left:-9999px" aria-hidden="true">
			<label>Website<input type="text" name="auditree_website" tabindex="-1" autocomplete="off"></label>
		</p>

		<p><button type="submit">Submit application</button></p>
	</form>
	<?php
	return ob_get_clean();
}
add_shortcode( 'auditree_apply', 'auditree_apply_shortcode' );

/**
 * Handle the form post and relay it to Odoo.
 */
function auditree_handle_apply() {
	$job_id      = (int) ( $_POST['job_id'] ?? 0 );
	$redirect_to = wp_validate_redirect( $_POST['redirect_to'] ?? '', home_url() );

	if ( ! $job_id || ! wp_verify_nonce( $_POST['auditree_nonce'] ?? '', 'auditree_apply_' . $job_id ) ) {
		wp_safe_redirect( add_query_arg( 'auditree_status', 'error', $redirect_to ) );
		exit;
	}

	// Honeypot filled means a bot. Report success so it does not retry, but
	// send nothing to Odoo.
	if ( ! empty( $_POST['auditree_website'] ) ) {
		wp_safe_redirect( add_query_arg( 'auditree_status', 'ok', $redirect_to ) );
		exit;
	}

	$fields = array(
		'job_id'   => (string) $job_id,
		'name'     => sanitize_text_field( $_POST['name'] ?? '' ),
		'email'    => sanitize_email( $_POST['email'] ?? '' ),
		'phone'    => sanitize_text_field( $_POST['phone'] ?? '' ),
		'linkedin' => esc_url_raw( $_POST['linkedin'] ?? '' ),
		'letter'   => sanitize_textarea_field( $_POST['letter'] ?? '' ),
	);

	$cv = null;
	if ( ! empty( $_FILES['cv']['tmp_name'] ) && is_uploaded_file( $_FILES['cv']['tmp_name'] ) ) {
		$checked = wp_check_filetype( $_FILES['cv']['name'] );
		if ( $checked['ext'] ) {
			$cv = array(
				'name' => $_FILES['cv']['name'],
				'type' => $checked['type'],
				'body' => file_get_contents( $_FILES['cv']['tmp_name'] ),
			);
		}
	}

	$result = auditree_submit_application( $fields, $cv );

	wp_safe_redirect( add_query_arg( 'auditree_status', $result, $redirect_to ) );
	exit;
}
add_action( 'admin_post_nopriv_auditree_apply', 'auditree_handle_apply' );
add_action( 'admin_post_auditree_apply', 'auditree_handle_apply' );

/**
 * POST an application to Odoo.
 *
 * Kept separate from the form handling above so that swapping the front end
 * for Gravity Forms, WPForms or Elementor means rewriting only the handler.
 *
 * WordPress's HTTP API has no multipart helper, so the body is assembled by
 * hand -- that is the only reason this function is as long as it is.
 *
 * @param array      $fields Flat string fields.
 * @param array|null $cv     array{name:string,type:string,body:string} or null.
 * @return string 'ok', 'duplicate' or 'error'.
 */
function auditree_submit_application( array $fields, $cv = null ) {
	if ( ! defined( 'AUDITREE_ODOO_URL' ) || ! defined( 'AUDITREE_ODOO_TOKEN' ) ) {
		error_log( 'Auditree: AUDITREE_ODOO_URL / AUDITREE_ODOO_TOKEN not defined in wp-config.php' );
		return 'error';
	}

	$boundary = wp_generate_password( 24, false );
	$eol      = "\r\n";
	$body     = '';

	foreach ( $fields as $key => $value ) {
		if ( '' === $value ) {
			continue;
		}
		$body .= '--' . $boundary . $eol;
		$body .= 'Content-Disposition: form-data; name="' . $key . '"' . $eol . $eol;
		$body .= $value . $eol;
	}

	if ( $cv ) {
		$body .= '--' . $boundary . $eol;
		$body .= 'Content-Disposition: form-data; name="cv"; filename="' .
			basename( $cv['name'] ) . '"' . $eol;
		$body .= 'Content-Type: ' . $cv['type'] . $eol . $eol;
		$body .= $cv['body'] . $eol;
	}

	$body .= '--' . $boundary . '--' . $eol;

	$response = wp_remote_post(
		AUDITREE_ODOO_URL . '/auditree/recruitment/apply',
		array(
			'timeout' => 20,
			'headers' => array(
				'Content-Type'      => 'multipart/form-data; boundary=' . $boundary,
				'X-Auditree-Token'  => AUDITREE_ODOO_TOKEN,
			),
			'body'    => $body,
		)
	);

	if ( is_wp_error( $response ) ) {
		error_log( 'Auditree: application relay failed: ' . $response->get_error_message() );
		return 'error';
	}

	$decoded = json_decode( wp_remote_retrieve_body( $response ), true );
	$status  = $decoded['status'] ?? 'error';

	if ( 'ok' !== $status && 'duplicate' !== $status ) {
		// Log the Odoo-side reason; never show it to the candidate.
		error_log( 'Auditree: Odoo rejected an application: ' .
			wp_remote_retrieve_body( $response ) );
		return 'error';
	}

	return $status;
}
