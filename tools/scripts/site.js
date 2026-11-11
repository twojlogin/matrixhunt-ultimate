/* Wspólny kod stron: jeden deszcz matrixa, jedna lista źródeł, jeden label.
 *
 * Wycięte z 6 plików (index, offers, retro, flash, bookmarks, wiki), które
 * miały to samo wklejone ze zmienionymi nazwami zmiennych. Strony wołają
 * window.MH.matrixRain() i czytają window.MH.SOURCES — definicja jest jedna.
 */
(function () {
  // JEDYNA lista do filtra źródeł. Nazwy muszą być identyczne z `name`
  // scraperów (super().__init__) i z kolumną source w bazie — 'Epic' zamiast
  // 'Epic Games' dawał pustą listę. Tylko aktywne; zaparkowane widać w API.
  var SOURCES = ['ALL', 'GamerPower', 'Epic Games', 'Steam', 'GOG',
    'IndieGala', 'Reddit', 'LowcyGier'];

  function themeLabel(theme) {
    var labels = { matrix: '◐ MATRIX', night: '● NIGHT', day: '○ DAY' };
    return labels[theme] || labels.matrix;
  }

  function matrixRain() {
    var canvas = document.getElementById('matrix-bg');
    if (!canvas || !canvas.getContext) return;
    var ctx = canvas.getContext('2d');
    function resize() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);
    var chars = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEF';
    var fs = 14;
    var cols = Math.floor(canvas.width / fs);
    var drops = new Array(cols).fill(1);
    function drawMatrix() {
      if (window.mhTheme && !window.mhTheme.isMatrix()) return;
      ctx.fillStyle = 'rgba(0,0,0,0.05)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#0f0';
      ctx.font = fs + 'px monospace';
      for (var i = 0; i < drops.length; i++) {
        ctx.fillText(chars[Math.floor(Math.random() * chars.length)], i * fs, drops[i] * fs);
        if (drops[i] * fs > canvas.height && Math.random() > 0.975) drops[i] = 0;
        drops[i]++;
      }
    }
    setInterval(drawMatrix, 50);
  }

  window.MH = window.MH || {};
  window.MH.SOURCES = SOURCES;
  window.MH.themeLabel = themeLabel;
  window.MH.matrixRain = matrixRain;
})();
