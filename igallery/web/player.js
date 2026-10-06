const localPhoto = /^\/api\/photo\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export function createPlayer({ fetchList, loadImage, showImage, wait }) {
  let photos = [], index = 0, interval = 30000, visible = false, pending = null;
  function preload(url) {
    return loadImage(url).then(image => ({image}), () => null);
  }
  return {
    async step() {
      if (index >= photos.length) {
        try {
          const data = await fetchList();
          if (!Array.isArray(data.photos)) throw Error('Invalid playlist');
          const next = data.photos.filter(p => localPhoto.test(p.url));
          photos = next;
          if (Number.isFinite(data.interval_seconds) && data.interval_seconds > 0) {
            interval = data.interval_seconds * 1000;
          }
        } catch { /* Keep the last playlist during service outages. */ }
        index = 0;
        pending = null;
      }
      if (!photos.length) { await wait(5000); return; }
      if (visible) await wait(interval);
      while (index < photos.length) {
        const url = photos[index++].url;
        const ready = pending || preload(url);
        pending = null;
        const loaded = await ready;
        if (loaded) {
          showImage(url, loaded.image);
          visible = true;
          if (index < photos.length) pending = preload(photos[index].url);
          return;
        }
      }
      await wait(5000);
    }
  };
}
