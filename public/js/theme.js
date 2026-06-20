(function() {
  var _fontStyleId = 'theme-custom-font';

  function applyTheme(d) {
    var r = document.documentElement;
    var b = document.body;
    if (!d || !d.success) return;

    // Primary color
    if (d.color) {
      r.style.setProperty('--theme-color', d.color);
      r.style.setProperty('--theme-color-light', d.color + '18');
      r.style.setProperty('--theme-color-lighter', d.color + '0c');
      r.style.setProperty('--theme-color-border', d.color + '40');
      r.style.setProperty('--theme-color-hover', d.color + 'cc');
    }
    // Background
    if (d.bg) {
      r.style.setProperty('--theme-bg-img', 'url(' + JSON.stringify(d.bg) + ')');
      b.style.backgroundImage = 'url(' + d.bg + ')';
      b.style.backgroundSize = 'cover';
      b.style.backgroundPosition = 'center';
      b.style.backgroundAttachment = 'fixed';
    } else {
      r.style.setProperty('--theme-bg-img', 'none');
      b.style.backgroundImage = '';
      b.style.backgroundColor = '';
    }
    // Font
    if (d.font) {
      r.style.setProperty('--theme-font', d.font);
      b.style.fontFamily = d.font + ', -apple-system, BlinkMacSystemFont, sans-serif';
    }
    // Custom font via @font-face (replace previous to avoid style tag leak)
    if (d.fontUrl) {
      var old = document.getElementById(_fontStyleId);
      if (old) old.remove();
      var style = document.createElement('style');
      style.id = _fontStyleId;
      style.textContent = "@font-face { font-family: 'Custom Font'; src: url('" + d.fontUrl + "'); font-display: swap; }";
      document.head.appendChild(style);
      r.style.setProperty('--theme-font', "'Custom Font'");
    }
    // Border radius
    if (d.radius) {
      r.style.setProperty('--theme-radius', d.radius + 'px');
    }
    // Shadow intensity
    if (d.shadow) {
      r.style.setProperty('--theme-shadow', d.shadow);
    }
    // Dark mode
    if (d.dark === 'true' || d.dark === true) {
      r.style.setProperty('--theme-bg-page', '#1a1a2e');
      r.style.setProperty('--theme-bg-card', '#232340');
      r.style.setProperty('--theme-bg-elevated', '#2a2a4a');
      r.style.setProperty('--theme-text', '#e0e0e0');
      r.style.setProperty('--theme-text-secondary', '#a0a0b0');
      r.style.setProperty('--theme-border', '#333355');
    } else {
      r.style.setProperty('--theme-bg-page', '#f0f2f5');
      r.style.setProperty('--theme-bg-card', '#ffffff');
      r.style.setProperty('--theme-bg-elevated', '#ffffff');
      r.style.setProperty('--theme-text', '#1a1a2e');
      r.style.setProperty('--theme-text-secondary', '#666666');
      r.style.setProperty('--theme-border', '#e0e0e0');
    }
    // Font size scale
    if (d.fontSize) {
      r.style.setProperty('--theme-font-size', d.fontSize);
    }
    // Gradient
    if (d.gradient) {
      r.style.setProperty('--theme-gradient', d.gradient);
      b.style.backgroundImage = d.gradient;
      b.style.backgroundAttachment = 'fixed';
    } else if (!d.bg) {
      r.style.setProperty('--theme-gradient', 'none');
    }
    // Blur
    if (d.blur) {
      r.style.setProperty('--theme-blur', d.blur + 'px');
    }
    // Animation
    if (d.animation === 'false' || d.animation === false) {
      r.style.setProperty('--theme-animation', '0');
    } else {
      r.style.setProperty('--theme-animation', '1');
    }
    // Layout density
    if (d.density) {
      r.style.setProperty('--theme-density', d.density);
    }
    // Preset name
    if (d.preset) {
      r.style.setProperty('--theme-preset', d.preset);
    }
  }

  function fetchTheme() {
    fetch('/api/theme').then(function(res){ return res.json(); }).then(applyTheme).catch(function(){});
  }

  // Apply immediately on load
  fetchTheme();
  // Then poll every 3 seconds for live updates
  setInterval(fetchTheme, 3000);
})();
