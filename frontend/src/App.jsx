// Dashboard UI (same as before). Replace BACKEND_BASE in .env when deploying.
import React, { useState, useEffect, useRef } from "react";

export default function App() {
  const [file, setFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [imageUrl, setImageUrl] = useState("");
  const [description, setDescription] = useState("");
  const [caption, setCaption] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [queue, setQueue] = useState([]);
  const [scheduledTime, setScheduledTime] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  const fileInputRef = useRef(null);

  useEffect(() => {
    fetchQueue();
  }, []);

  async function fetchQueue() {
    try {
      const res = await fetch("/api/queue");
      if (!res.ok) throw new Error("Failed to fetch queue");
      const data = await res.json();
      setQueue(data);
    } catch (e) {
      console.error(e);
    }
  }

  function handleFileChange(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setImagePreview(URL.createObjectURL(f));
    setDescription((prev) => prev || `Photo: ${f.name.replace(/[-_]/g, " ")}`);
  }

  async function handleUpload() {
    if (!file) return setMessage({ type: "error", text: "Choose a file first" });
    setLoading(true);
    setMessage(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      setImageUrl(data.imageUrl);
      setMessage({ type: "success", text: "Image uploaded" });
    } catch (e) {
      console.error(e);
      setMessage({ type: "error", text: e.message || "Upload error" });
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateCaption() {
    if (!description && !imageUrl && !imagePreview) {
      return setMessage({ type: "error", text: "Provide an image or description to generate caption" });
    }
    setIsGenerating(true);
    setMessage(null);
    try {
      const res = await fetch("/api/generate_caption", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageDescription: description }),
      });
      if (!res.ok) throw new Error("Caption generation failed");
      const data = await res.json();
      setCaption(data.caption);
    } catch (e) {
      console.error(e);
      setMessage({ type: "error", text: e.message || "Generate error" });
    } finally {
      setIsGenerating(false);
    }
  }

  async function handlePublishNow() {
    setLoading(true);
    setMessage(null);
    try {
      let finalImageUrl = imageUrl;
      if (!finalImageUrl && file) {
        const fd = new FormData();
        fd.append("file", file);
        const up = await fetch("/api/upload", { method: "POST", body: fd });
        if (!up.ok) throw new Error("Upload failed");
        const upData = await up.json();
        finalImageUrl = upData.imageUrl;
        setImageUrl(finalImageUrl);
      }
      if (!finalImageUrl) throw new Error("No image URL available");

      const createRes = await fetch("/api/create_media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageUrl: finalImageUrl, caption }),
      });
      if (!createRes.ok) throw new Error("Create media failed");
      const createData = await createRes.json();

      const publishRes = await fetch("/api/publish_media", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ creation_id: createData.creation_id }),
      });
      if (!publishRes.ok) throw new Error("Publish failed");
      const pubData = await publishRes.json();
      setMessage({ type: "success", text: `Published — id: ${pubData.id || pubData.post_id || "unknown"}` });
      fetchQueue();
    } catch (e) {
      console.error(e);
      setMessage({ type: "error", text: e.message || "Publish error" });
    } finally {
      setLoading(false);
    }
  }

  async function handleSchedule() {
    if (!scheduledTime) return setMessage({ type: "error", text: "Pick a schedule time" });
    setLoading(true);
    setMessage(null);
    try {
      let finalImageUrl = imageUrl;
      if (!finalImageUrl && file) {
        const fd = new FormData();
        fd.append("file", file);
        const up = await fetch("/api/upload", { method: "POST", body: fd });
        if (!up.ok) throw new Error("Upload failed");
        const upData = await up.json();
        finalImageUrl = upData.imageUrl;
        setImageUrl(finalImageUrl);
      }
      const res = await fetch("/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageUrl: finalImageUrl, caption, scheduleTime: scheduledTime }),
      });
      if (!res.ok) throw new Error("Schedule failed");
      const data = await res.json();
      setMessage({ type: "success", text: `Scheduled (job: ${data.jobId})` });
      fetchQueue();
    } catch (e) {
      console.error(e);
      setMessage({ type: "error", text: e.message || "Schedule error" });
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteJob(id) {
    try {
      const res = await fetch(`/api/queue/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Delete failed");
      setMessage({ type: "success", text: "Deleted" });
      fetchQueue();
    } catch (e) {
      console.error(e);
      setMessage({ type: "error", text: e.message || "Delete error" });
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        <header className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold">Instagram Daily Post — Dashboard</h1>
            <p className="text-sm text-gray-600">Create, preview, schedule and publish daily Instagram posts.</p>
          </div>
          <div className="flex gap-2">
            <button
              className="px-4 py-2 bg-white border rounded shadow-sm text-sm"
              onClick={() => { setFile(null); setImagePreview(null); setImageUrl(""); setCaption(""); setDescription(""); }}
            >
              Reset
            </button>
            <button
              className="px-4 py-2 bg-indigo-600 text-white rounded shadow-sm text-sm"
              onClick={fetchQueue}
            >
              Refresh Queue
            </button>
          </div>
        </header>

        <main className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <section className="col-span-1 bg-white p-4 rounded shadow-sm">
            <h2 className="font-medium mb-2">Upload / Image</h2>
            <div className="mb-3">
              <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileChange} />
            </div>
            {imagePreview && (
              <div className="mb-3">
                <img src={imagePreview} alt="preview" className="w-full object-cover rounded" />
              </div>
            )}
            {imageUrl && (
              <div className="mb-3">
                <label className="text-xs text-gray-500">Uploaded URL</label>
                <div className="text-sm break-all text-blue-600">{imageUrl}</div>
              </div>
            )}

            <div className="mb-3">
              <label className="block text-sm font-medium text-gray-700">Image description (for caption gen)</label>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1 w-full p-2 border rounded" rows={3} />
            </div>

            <div className="flex gap-2">
              <button onClick={handleUpload} className="px-3 py-2 bg-green-600 text-white rounded" disabled={loading}>
                Upload
              </button>
              <button onClick={handleGenerateCaption} className="px-3 py-2 bg-yellow-500 rounded" disabled={isGenerating}>
                {isGenerating ? "Generating..." : "Generate Caption"}
              </button>
            </div>

            <div className="mt-4">
              <label className="block text-sm font-medium text-gray-700">Caption</label>
              <textarea value={caption} onChange={(e) => setCaption(e.target.value)} className="mt-1 w-full p-2 border rounded" rows={4} />
            </div>

            <div className="mt-4">
              <label className="block text-sm font-medium text-gray-700">Schedule time (IST)</label>
              <input type="datetime-local" value={scheduledTime} onChange={(e) => setScheduledTime(e.target.value)} className="mt-1 w-full p-2 border rounded" />
            </div>

            <div className="mt-4 flex gap-2">
              <button onClick={handlePublishNow} className="px-4 py-2 bg-blue-600 text-white rounded" disabled={loading}>
                Publish Now
              </button>
              <button onClick={handleSchedule} className="px-4 py-2 bg-indigo-500 text-white rounded" disabled={loading}>
                Schedule
              </button>
            </div>

            {message && (
              <div className={`mt-4 p-3 rounded ${message.type === 'error' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                {message.text}
              </div>
            )}
          </section>

          <section className="col-span-1 md:col-span-2 bg-white p-4 rounded shadow-sm">
            <h2 className="font-medium mb-2">Preview & Queue</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="border rounded p-4 flex flex-col">
                <div className="mb-3 text-sm text-gray-500">Post Preview</div>
                <div className="flex-1 border rounded p-3 flex flex-col">
                  {imagePreview || imageUrl ? (
                    <img src={imagePreview || imageUrl} alt="post preview" className="w-full h-48 object-cover rounded mb-3" />
                  ) : (
                    <div className="w-full h-48 bg-gray-100 rounded mb-3 flex items-center justify-center text-gray-400">No image</div>
                  )}
                  <div className="text-sm text-gray-700 whitespace-pre-wrap">{caption || "Your caption will appear here."}</div>
                </div>

                <div className="mt-3 text-xs text-gray-500">Tip: keep captions <= 2,200 characters. Instagram shows ~125 chars before a "more" link.</div>
              </div>

              <div className="border rounded p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="text-sm text-gray-500">Queued / Scheduled Posts</div>
                  <button className="text-xs text-blue-600" onClick={fetchQueue}>Refresh</button>
                </div>
                <div className="space-y-3 max-h-96 overflow-auto">
                  {queue.length === 0 && <div className="text-sm text-gray-400">No scheduled posts</div>}
                  {queue.map((job) => (
                    <div key={job.id} className="flex items-start gap-3 p-2 border rounded">
                      <img src={job.imageUrl} alt="q" className="w-16 h-16 object-cover rounded" />
                      <div className="flex-1">
                        <div className="text-sm font-medium">{job.caption?.slice(0, 80) || "(no caption)"}</div>
                        <div className="text-xs text-gray-500">{job.scheduledAt ? new Date(job.scheduledAt).toLocaleString() : job.status}</div>
                      </div>
                      <div className="flex flex-col gap-2">
                        <button className="px-2 py-1 bg-red-500 text-white rounded text-xs" onClick={() => handleDeleteJob(job.id)}>Delete</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-6 text-xs text-gray-500">Connected account: <span className="font-medium">(Connect via backend)</span></div>
          </section>
        </main>

        <footer className="mt-6 text-center text-xs text-gray-500">Built with ❤️ — connect your backend to enable publish & schedule features.</footer>
      </div>
    </div>
  );
}
