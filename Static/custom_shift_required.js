// This script disables required fields in job modals when 'Custom Shift' is selected
function handleCustomShiftRequiredFields(modalPrefix) {
    const jobTypeSelect = document.getElementById(modalPrefix + 'JobType');
    if (!jobTypeSelect) return;
    const requiredFields = [
        document.querySelector(`input[name='job_name']#${modalPrefix}JobName`),
        document.querySelector(`input[name='po_number']#${modalPrefix}PoNumber`),
        document.querySelector(`input[name='address']#${modalPrefix}Address`),
        document.querySelector(`input[name='phone_number']#${modalPrefix}Phone`),
        document.querySelector(`input[name='story']#${modalPrefix}Story`)
    ];
    function updateRequired() {
        const isCustom = jobTypeSelect.value === 'Custom Shift';
        requiredFields.forEach(f => {
            if (f) f.required = !isCustom;
        });
    }
    jobTypeSelect.addEventListener('change', updateRequired);
    updateRequired();
}

document.addEventListener('DOMContentLoaded', function() {
    handleCustomShiftRequiredFields('quick');
    handleCustomShiftRequiredFields('calSlot');
    handleCustomShiftRequiredFields('edit');
});
