// Shared form client script (used by all three modules).
// Expected: Each form template defines `modulePrefix` JS variable (e.g. "/hvac-mep")
// Usage: include this once in <script src="{{ url_for('static', filename='form.js') }}"></script>

async function loadDropdowns(modulePrefix, onLoaded) {
    try {
        const res = await fetch(`${modulePrefix}/dropdowns`);
        if (res.ok) {
            const d = await res.json();
            if (onLoaded) onLoaded(d);
            return d;
        }
    } catch (e) {
        console.warn("Could not load dropdowns", e);
    }
    return {};
}

function initSignaturePads() {
    if (typeof SignaturePad === 'undefined') return {};
    const techCanvas = document.getElementById('techSignaturePad');
    const opManCanvas = document.getElementById('opManSignaturePad');
    const pads = {};
    if (techCanvas) pads.tech = new SignaturePad(techCanvas, {backgroundColor: 'rgb(255,255,255)'});
    if (opManCanvas) pads.op = new SignaturePad(opManCanvas, {backgroundColor: 'rgb(255,255,255)'});
    return pads;
}

async function collectSignatureData(pad) {
    if (!pad || pad.isEmpty()) return null;
    const dataURL = pad.toDataURL('image/png');
    const res = await fetch(dataURL);
    const blob = await res.blob();
    return blob;
}

async function submitForm(modulePrefix, formElement, pads) {
    const fd = new FormData(formElement);
    // capture signatures
    if (pads && pads.tech) {
        const b = await collectSignatureData(pads.tech);
        if (b) fd.append('tech_signature', b, 'tech_signature.png');
    }
    if (pads && pads.op) {
        const b2 = await collectSignatureData(pads.op);
        if (b2) fd.append('op_signature', b2, 'op_signature.png');
    }
    // post
    const submitUrl = `${modulePrefix}/submit`;
    const resp = await fetch(submitUrl, {method: 'POST', body: fd});
    if (!resp.ok) {
        const text = await resp.text();
        throw new Error('Submit failed: ' + text);
    }
    const data = await resp.json();
    return data; // {job_id, submission_id}
}

async function pollJobStatus(modulePrefix, jobId, onUpdate, interval=1500) {
    const statusUrl = `${modulePrefix}/status/${jobId}`;
    return new Promise((resolve, reject) => {
        const id = setInterval(async () => {
            try {
                const r = await fetch(statusUrl);
                if (!r.ok) throw new Error('Job not found');
                const js = await r.json();
                if (onUpdate) onUpdate(js);
                // Check both 'state' (legacy) and 'status' (current)
                const isDone = js.state === 'done' || js.status === 'completed';
                const isFailed = js.state === 'failed' || js.status === 'failed';
                if (isDone || isFailed) {
                    clearInterval(id);
                    resolve(js);
                }
            } catch (e) {
                clearInterval(id);
                reject(e);
            }
        }, interval);
    });
}