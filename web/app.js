const form = document.querySelector('#generate-form');
const jobsEl = document.querySelector('#jobs');
const message = document.querySelector('#form-message');
const shotFields = document.querySelector('#shot-fields');
const storyboardFields = document.querySelector('#storyboard-fields');
const shotList = document.querySelector('#shot-list');
let mode = 'shot';

const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
})[character]);

function addShot(value = '') {
  if (shotList.children.length >= 12) return;
  const row = document.createElement('div');
  row.className = 'shot-row';
  row.innerHTML = `<b></b><div class="shot-content"><textarea class="shot-prompt" minlength="12" maxlength="1200" placeholder="Describe this shot's subject, action, camera, lighting, and environment">${esc(value)}</textarea><textarea class="shot-narration" maxlength="600" placeholder="Optional narration for this shot"></textarea></div><button type="button" aria-label="Remove shot">×</button>`;
  row.querySelector('button').addEventListener('click', () => {
    if (shotList.children.length > 2) {
      row.remove();
      renumberShots();
    }
  });
  shotList.appendChild(row);
  renumberShots();
}

function renumberShots() {
  [...shotList.children].forEach((row, index) => row.querySelector('b').textContent = index + 1);
}

function setMode(next) {
  mode = next;
  shotFields.hidden = mode !== 'shot';
  storyboardFields.hidden = mode !== 'storyboard';
  document.querySelectorAll('.mode-switch button').forEach(button => {
    button.classList.toggle('active', button.dataset.mode === mode);
  });
}

document.querySelectorAll('.mode-switch button').forEach(button => {
  button.addEventListener('click', () => setMode(button.dataset.mode));
});
document.querySelector('#add-shot').addEventListener('click', () => addShot());
addShot('Wide establishing shot: a spacecraft approaches Venus as sunlight cuts across the planet, smooth orbital camera movement.');
addShot('Close tracking shot: the probe enters turbulent amber clouds, atmospheric particles rushing past the lens, stable spacecraft geometry.');

async function loadJobs() {
  try {
    const jobs = await fetch('/api/jobs').then(response => response.json());
    jobsEl.innerHTML = jobs.length ? jobs.map(job => {
      const label = job.spec.kind === 'storyboard' ? job.spec.title : job.spec.prompt;
      const meta = job.spec.kind === 'storyboard'
        ? `${job.spec.shots.length} shots · ${job.spec.preset}`
        : `${job.spec.preset} · ${job.spec.aspect}`;
      const retry = ['failed', 'cancelled'].includes(job.status) ? `<button class="retry" data-job="${job.id}">Retry</button>` : '';
      return `<article class="job"><div class="job-top"><strong>${esc(label.slice(0, 48))}${label.length > 48 ? '…' : ''}</strong><span class="status">${esc(job.status)}</span></div><p>${esc(meta)}</p><div class="bar"><i style="width:${Number(job.progress) || 0}%"></i></div>${job.status === 'completed' ? `<p><a href="/api/jobs/${job.id}/video">Open video</a></p>` : ''}${job.error ? `<p>${esc(job.error)}</p>` : ''}${retry}</article>`;
    }).join('') : '<p>No renders queued.</p>';
    jobsEl.querySelectorAll('.retry').forEach(button => button.addEventListener('click', async () => {
      await fetch(`/api/jobs/${button.dataset.job}/retry`, { method: 'POST' });
      loadJobs();
    }));
  } catch {
    jobsEl.innerHTML = '<p>Queue unavailable.</p>';
  }
}

async function uploadReference() {
  const file = document.querySelector('#source-image').files[0];
  if (!file) return null;
  const body = new FormData();
  body.append('file', file);
  const response = await fetch('/api/uploads', { method: 'POST', body });
  const uploaded = await response.json();
  if (!response.ok) throw new Error(uploaded.detail || 'Reference image upload failed.');
  return uploaded.path;
}

async function uploadMusic() {
  const file = document.querySelector('#music-file').files[0];
  if (!file) return null;
  const body = new FormData();
  body.append('file', file);
  const response = await fetch('/api/uploads/audio', { method: 'POST', body });
  const uploaded = await response.json();
  if (!response.ok) throw new Error(uploaded.detail || 'Soundtrack upload failed.');
  return uploaded.path;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  message.textContent = 'Preparing render…';
  try {
    let endpoint = '/api/jobs';
    let payload;
    if (mode === 'storyboard') {
      const shots = [...shotList.querySelectorAll('.shot-row')].map(row => ({
        prompt: row.querySelector('.shot-prompt').value,
        narration: row.querySelector('.shot-narration').value
      }));
      payload = {
        title: document.querySelector('#storyboard-title').value,
        aspect: document.querySelector('#aspect').value,
        preset: document.querySelector('#preset').value,
        seed: Number(document.querySelector('#seed').value),
        continuity: document.querySelector('#continuity').checked,
        captions: document.querySelector('#burn-captions').checked,
        music_path: await uploadMusic(),
        music_volume: Number(document.querySelector('#music-volume').value),
        shots
      };
      endpoint = '/api/storyboards';
    } else {
      payload = {
        prompt: document.querySelector('#prompt').value,
        negative_prompt: document.querySelector('#negative').value,
        aspect: document.querySelector('#aspect').value,
        preset: document.querySelector('#preset').value,
        seed: Number(document.querySelector('#seed').value),
        source_image: await uploadReference()
      };
    }
    const response = await fetch(endpoint, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not queue render.');
    message.textContent = `Queued ${data.id.slice(0, 8)}. The local GPU worker will render it.`;
    loadJobs();
  } catch (error) {
    message.textContent = error.message;
  }
});

loadJobs();
setInterval(loadJobs, 3000);
