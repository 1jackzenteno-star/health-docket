/* Health Docket -- shared client-side helpers for the live frontend
   (Task 10). Every real value on every page comes from a fetch() call
   here against the JSON API -- nothing is hardcoded, per design spec
   §7's "swap a hardcoded array for a fetch() call" and NFR4. */

var Docket = (function () {
  function fetchJSON(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (body) {
          var msg = (body && body.detail) ? body.detail : (url + ": HTTP " + r.status);
          throw new Error(msg);
        });
      }
      return r.json();
    });
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function fmtDate(iso) {
    if (!iso) return "date unknown";
    var d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  var TIER_LABEL = { federal: "Federal", state: "NV Legislature", local: "NV local" };
  function tierLabel(key) { return TIER_LABEL[key] || key; }

  // Combined document-status badge per design spec §3.3's empty-state
  // ladder: not linked -> linked -> captured -> extraction pending ->
  // extracted. "extraction failed" is a real, distinct schema state
  // (extraction_status = 'failed') shown honestly rather than folded
  // back into an earlier state or hidden.
  function docStatusBadge(doc) {
    var cap = doc.capture_status, ext = doc.extraction_status;
    if (cap === "not_linked" || !cap) return { label: "not linked", cls: "doc-notlinked" };
    if (cap === "linked") return { label: "linked", cls: "doc-pending" };
    // cap === 'captured'
    if (ext === "extracted") return { label: "extracted", cls: "doc-extracted" };
    if (ext === "failed") return { label: "extraction failed", cls: "doc-failed" };
    return { label: "extraction pending", cls: "doc-pending" };
  }

  function sparklineSVG(counts) {
    if (!counts || !counts.length) return "";
    var w = 84, h = 22, max = Math.max.apply(null, counts.concat([1]));
    var step = w / Math.max(counts.length - 1, 1);
    var pts = counts.map(function (c, i) {
      var x = i * step;
      var y = h - (c / max) * (h - 4) - 2;
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    return '<svg class="sparkline" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
      '<polyline points="' + pts + '"/></svg>';
  }

  function breadcrumbsHTML(items) {
    // items: [{label, href}], last item has no href (current page)
    var parts = items.map(function (item, i) {
      var isLast = i === items.length - 1;
      if (isLast || !item.href) {
        return '<span class="current">' + escapeHtml(item.label) + "</span>";
      }
      return '<a href="' + item.href + '">' + escapeHtml(item.label) + "</a>";
    });
    return parts.join('<span class="sep">&rsaquo;</span>');
  }

  function el(tag, className, html) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (html !== undefined) node.innerHTML = html;
    return node;
  }

  function showError(container, err) {
    container.innerHTML = '<div class="error-banner">Couldn\'t load this from the API: ' +
      escapeHtml(err && err.message ? err.message : String(err)) + "</div>";
  }

  return {
    fetchJSON: fetchJSON,
    escapeHtml: escapeHtml,
    fmtDate: fmtDate,
    tierLabel: tierLabel,
    docStatusBadge: docStatusBadge,
    sparklineSVG: sparklineSVG,
    breadcrumbsHTML: breadcrumbsHTML,
    el: el,
    showError: showError,
  };
})();
