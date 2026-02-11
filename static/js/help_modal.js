/**
 * Authors: Benjamin Lindeen, Austin Jacobson
 * @file help_modal.js
 * This file is used to handle the help modals on the connect and downlinks pages.
 * It contains the following functions:
 * - openHelpModal(modalId)
 * - closeHelpModal(modalId)
 * - window.onclick(event)
 * - document.addEventListener('DOMContentLoaded', (event))
 */


/**
 * This script is used to open and close help modals.
 * It is used in the help button on the connect and downlinks pages.
 * @param event - The event object
 * @returns {void}
 */
document.addEventListener('DOMContentLoaded', (event) => {
    document.querySelectorAll('.help-button').forEach(button => {
        button.addEventListener('click', (event) => {
            const modalId = event.target.getAttribute('data-modal');
            openHelpModal(modalId);
        });
    });

    window.onclick = function (event) {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            if (event.target === modal) {
                modal.style.display = 'none';
            }
        });
    }
});

/**
 * Open the help modal with the given modal
 * @param modalId - The ID of the modal to open
 * @returns {void}
 */
function openHelpModal(modalId) {
    const helpModal = document.getElementById(modalId);
    if (helpModal) {
        helpModal.style.display = 'block';
    }
}

/**
 * Close the help modal with the given modal
 * @param modalId - The ID of the modal to close
 * @returns {void}
 */
function closeHelpModal(modalId) {
    const helpModal = document.getElementById(modalId);
    if (helpModal) {
        helpModal.style.display = 'none';
    }
}

/**
 * Close the help modal when the user clicks outside of it
 * @param event - The event object
 * @returns {void}
 */
window.onclick = function (event) {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
}