import { createPlayer } from './player.js';

const slides = [...document.querySelectorAll('.slide')];
let active = 0;
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
  showImage(url, image) {
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
  },
  wait: ms => new Promise(resolve => setTimeout(resolve, ms))
});

while (true) await player.step();
