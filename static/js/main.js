// Wagestop — Main JavaScript
// Handles question flow visibility and UI interactions

document.addEventListener('DOMContentLoaded', function() {

  // --- QUESTION FLOW LOGIC ---
  const pensionEnrolled = document.getElementById('pension_enrolled');
  const knowsMin = document.getElementById('knows_min_contribution');
  const erMatching = document.getElementById('er_matching_type');
  const minWageCheck = document.getElementById('min_wage_check');
  const travelsClients = document.getElementById('travels_clients');
  const paidTravelTime = document.getElementById('paid_travel_time');
  const isApprentice = document.getElementById('is_apprentice');

  function showHide(elementId, show) {
    const el = document.getElementById(elementId);
    if (el) el.style.display = show ? 'block' : 'none';
  }

  if (pensionEnrolled) {
    pensionEnrolled.addEventListener('change', function() {
      const show = this.value === 'yes';
      showHide('q3-block', show);
      showHide('q4-block', show);
      showHide('q5-block', false);
      showHide('q6-block', show);
      showHide('q7-block', false);
    });
  }

  if (knowsMin) {
    knowsMin.addEventListener('change', function() {
      showHide('q5-block', this.value === 'yes');
    });
  }

  if (erMatching) {
    erMatching.addEventListener('change', function() {
      showHide('q7-block', this.value === 'b');
    });
  }

  if (minWageCheck) {
    minWageCheck.addEventListener('change', function() {
      showHide('mw-block', this.value === 'yes');
    });
  }

  if (travelsClients) {
    travelsClients.addEventListener('change', function() {
      const show = this.value === 'yes';
      showHide('mw8-block', show);
      showHide('mw9-block', show);
      showHide('mw10-block', false);
    });
  }

  if (paidTravelTime) {
    paidTravelTime.addEventListener('change', function() {
      showHide('mw10-block', this.value === 'no');
    });
  }

  if (isApprentice) {
    isApprentice.addEventListener('change', function() {
      showHide('mw4-block', this.value === 'yes');
    });
  }

  // Q5c mutual exclusivity — entering total clears a/b
  const totalPct = document.getElementById('ee_total_pct');
  const totalGbp = document.getElementById('ee_total_gbp');
  const minPct   = document.getElementById('ee_min_pct');
  const minGbp   = document.getElementById('ee_min_gbp');
  const addPct   = document.getElementById('ee_additional_pct');
  const addGbp   = document.getElementById('ee_additional_gbp');

  function clearAB() {
    if (minPct)  minPct.value  = '';
    if (minGbp)  minGbp.value  = '';
    if (addPct)  addPct.value  = '';
    if (addGbp)  addGbp.value  = '';
  }

  if (totalPct) totalPct.addEventListener('input', function() { if (this.value) clearAB(); });
  if (totalGbp) totalGbp.addEventListener('input', function() { if (this.value) clearAB(); });
});
