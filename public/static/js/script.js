// Form Validation + Loading Spinner (Analyzer page only)
const sentimentForm = document.getElementById("sentimentForm");

if (sentimentForm) {
    sentimentForm.addEventListener("submit", function(e) {

        const vote   = document.getElementById("vote").value;
        const review = document.getElementById("review").value.trim();
        const loader = document.getElementById("loader");
        const btn    = document.getElementById("analyzeBtn");

        if (vote === "" || review === "") {
            alert("Please fill all fields!");
            e.preventDefault();
            return;
        }

        // Show loading spinner
        loader.style.display = "block";

        // Disable button
        btn.disabled = true;
    });
}