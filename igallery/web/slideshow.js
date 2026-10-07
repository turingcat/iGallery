import { createPlayer } from './player.js';

const slides = [...document.querySelectorAll('.slide')];
let active = 0;
const dateLabel = document.querySelector('#taken-date');
let colorFrame;

function updateDateColor() {
  cancelAnimationFrame(colorFrame);
  if (dateLabel.hidden) return;
  const box = dateLabel.getBoundingClientRect();
  const canvas = document.createElement('canvas');
  canvas.width = 32; canvas.height = 8;
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, 32, 8);
  let fading = false;
  // Match DOM paint order, contain letterboxing and the visible crossfade.
  for (const image of slides) {
    if (!image.naturalWidth) continue;
    const opacity = Number(getComputedStyle(image).opacity);
    fading ||= image.classList.contains('active') ? opacity < 1 : opacity > 0;
    const frame = image.getBoundingClientRect();
    const scale = Math.min(frame.width / image.naturalWidth, frame.height / image.naturalHeight);
    const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
    const x = frame.left + (frame.width - width) / 2;
    const y = frame.top + (frame.height - height) / 2;
    ctx.globalAlpha = opacity;
    ctx.drawImage(image, (x - box.left) * 32 / box.width, (y - box.top) * 8 / box.height,
      width * 32 / box.width, height * 8 / box.height);
  }
  const pixels = ctx.getImageData(0, 0, 32, 8).data;
  let luminance = 0;
  const linear = value => { const s = value / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4; };
  for (let i = 0; i < pixels.length; i += 4) {
    luminance += .2126 * linear(pixels[i]) + .7152 * linear(pixels[i + 1]) + .0722 * linear(pixels[i + 2]);
  }
  const light = luminance / (32 * 8) > .179;
  dateLabel.style.color = light ? '#000' : '#fff';
  const shadow = light ? '#fff' : '#000';
  dateLabel.style.textShadow = `0 1px 3px ${shadow}, 0 0 2px ${shadow}`;
  if (fading) colorFrame = requestAnimationFrame(updateDateColor);
}

window.addEventListener('resize', updateDateColor);
const player = createPlayer({
  async fetchList() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch('/api/photos', {signal: controller.signal, cache: 'no-store'});
      if (!response.ok) throw Error('Playlist unavailable');
      return await response.json();
    } finally { clearTimeout(timer); }
  },
  loadImage(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      const timer = setTimeout(() => finish(false), 10000);
      function finish(ok) {
        clearTimeout(timer); image.onload = image.onerror = null;
        if (ok) resolve(image); else { image.src = ''; reject(Error('Image unavailable')); }
      }
      image.onload = () => image.decode().then(() => finish(true), () => finish(false));
      image.onerror = () => finish(false);
      image.src = url;
    });
  },
  showImage(url, image, date) {
    const next = 1 - active;
    image.className = 'slide';
    image.alt = '';
    image.draggable = false;
    slides[next].replaceWith(image);
    slides[next] = image;
    // Commit the initial opacity before revealing the already-decoded image.
    void image.offsetWidth;
    image.classList.add('active');
    slides[active].classList.remove('active');
    active = next;
    document.querySelector('#waiting').hidden = true;
    dateLabel.textContent = date || '';
    dateLabel.dateTime = date || '';
    dateLabel.hidden = !date;
    updateDateColor();
  },
  wait: ms => new Promise(resolve => setTimeout(resolve, ms))
});

while (true) await player.step();
