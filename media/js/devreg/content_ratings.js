/* IARC content ratings. */
define('iarc-ratings', [], function() {

    // Poll to see if IARC rating process finished.
    var $createRating = $('.create-rating:not(.loading)');
    var $createBtn = $('.create-iarc-rating', $createRating);
    var apiUrl = $createBtn.data('api-url');
    var redirectUrl = $createBtn.data('redirect-url');

    $createBtn.on('click', function() {
        // Open window.
        var IARCPopUp = window.open($('form#iarc').attr('action'), 'IARCForm');

        // Spinner.
        $createRating.addClass('loading');
        var interval = setInterval(function() {
            // Poll content ratings API, checking if the IARC form is done.
            $.get(apiUrl, function(data) {
                if (!('objects' in data)) {
                    // Error.
                    $('.error').show();
                    $createRating.removeClass('loading');
                } else if (data.objects.length) {
                    // Redirect to summary page.
                    window.location = redirectUrl;
                    $('.done').show();
                    $createRating.removeClass('loading');
                }
            });

            // If IARC form window closed, remove the spinner.
            if (IARCPopUp === null || IARCPopUp.closed) {
                $createRating.removeClass('loading');
                window.clearInterval(interval);
            }
        }, 2000);
    });
});
