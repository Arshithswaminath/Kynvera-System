// static/site_form.js
// Client-side form handling for site visit.
// - Uploads images to Cloudinary unsigned preset
// - Submits metadata to /site-visit/api/submit/metadata
// - Allows calling finalize endpoint when visit created

(function () {
  const itemsContainer = document.getElementById('items');
  const addItemBtn = document.getElementById('add-item');
  const form = document.getElementById('visit-form');
  const feedback = document.getElementById('feedback');
  const submitBtn = document.getElementById('submit-btn');
  const finalizeBtn = document.getElementById('finalize-btn');

  let visitId = null;

  function newItemElement() {
    const wrapper = document.createElement('div');
    wrapper.className = 'item';

    wrapper.innerHTML = `
      <label>Title <input type="text" class="item-title" required /></label>
      <label>Description <textarea class="item-desc" rows="2"></textarea></label>
      <label>Upload photos <input type="file" accept="image/*" class="item-files" multiple /></label>
      <div class="images"></div>
      <div class="small">Uploaded URLs: <span class="uploaded-urls"></span></div>
      <button type="button" class="remove-item">Remove item</button>
    `;

    // store uploaded URLs on the wrapper element
    wrapper.uploaded = [];

    // hook file input
    const fileInput = wrapper.querySelector('.item-files');
    const imagesDiv = wrapper.querySelector('.images');
    const urlsSpan = wrapper.querySelector('.uploaded-urls');
    const removeBtn = wrapper.querySelector('.remove-item');

    fileInput.addEventListener('change', async (e) => {
      const files = Array.from(e.target.files || []);
      if (!files.length) return;
      for (const f of files) {
        const thumb = document.createElement('img');
        thumb.className = 'thumb';
        thumb.alt = 'uploading...';
        imagesDiv.appendChild(thumb);
        try {
          const res = await uploadToCloudinary(f, (pct) => {
            thumb.style.opacity = 0.6;
          });
          wrapper.uploaded.push(res.secure_url);
          thumb.src = res.secure_url;
          thumb.alt = '';
          urlsSpan.textContent = wrapper.uploaded.join(', ');
        } catch (err) {
          imagesDiv.removeChild(thumb);
          showError('Image upload failed: ' + (err.message || err));
        }
      }
    });

    removeBtn.addEventListener('click', () => {
      itemsContainer.removeChild(wrapper);
    });

    return wrapper;
  }

  function showFeedback(msg) {
    feedback.innerHTML = `<div class="status">${msg}</div>`;
  }
  function showError(msg) {
    feedback.innerHTML = `<div class="error">${msg}</div>`;
  }

  addItemBtn.addEventListener('click', () => {
    const el = newItemElement();
    itemsContainer.appendChild(el);
  });

  // Add one initial item
  itemsContainer.appendChild(newItemElement());

  async function uploadToCloudinary(file) {
    if (!window.CLOUDINARY_CLOUD_NAME || !window.CLOUDINARY_UPLOAD_PRESET) {
      throw new Error('Cloudinary not configured on the page.');
    }
    const url = `https://api.cloudinary.com/v1_1/${window.CLOUDINARY_CLOUD_NAME}/image/upload`;
    const fd = new FormData();
    fd.append('file', file);
    fd.append('upload_preset', window.CLOUDINARY_UPLOAD_PRESET);

    const r = await fetch(url, { method: 'POST', body: fd });
    if (!r.ok) {
      const text = await r.text();
      throw new Error('Cloudinary upload failed: ' + text);
    }
    return r.json();
  }

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    submitBtn.disabled = true;
    showFeedback('Submitting metadata…');

    try {
      // gather data
      const visit_info = {
        building_name: document.getElementById('building_name').value,
        email: document.getElementById('email').value,
        building_address: document.getElementById('building_address').value
      };

      const report_items = Array.from(itemsContainer.querySelectorAll('.item')).map((el) => {
        const title = el.querySelector('.item-title').value;
        const description = el.querySelector('.item-desc').value;
        const image_urls = (el.uploaded || []).slice(); // may be empty
        return { title, description, image_urls };
      });

      const signatures = {
        inspector_name: document.getElementById('inspector_name').value || ''
      };

      const payload = { visit_info, report_items, signatures };

      const resp = await fetch('/site-visit/api/submit/metadata', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error('Server returned ' + resp.status + ': ' + txt);
      }

      const data = await resp.json();
      visitId = data.visit_id || data.id || null;
      showFeedback('Metadata saved. visit_id: ' + visitId);
      finalizeBtn.disabled = false;
    } catch (err) {
      showError('Failed to submit metadata: ' + (err.message || err));
    } finally {
      submitBtn.disabled = false;
    }
  });

  finalizeBtn.addEventListener('click', async () => {
    if (!visitId) {
      showError('No visit_id. Submit metadata first.');
      return;
    }
    finalizeBtn.disabled = true;
    showFeedback('Finalizing (enqueueing) report…');
    try {
      const resp = await fetch(`/site-visit/api/submit/finalize?visit_id=${encodeURIComponent(visitId)}`);
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error('Server returned ' + resp.status + ': ' + txt);
      }
      const data = await resp.json();
      showFeedback('Finalize accepted. Poll status at: ' + (data.status_url || `/site-visit/api/report-status?visit_id=${visitId}`));
    } catch (err) {
      showError('Finalize failed: ' + (err.message || err));
    } finally {
      finalizeBtn.disabled = false;
    }
  });

})();