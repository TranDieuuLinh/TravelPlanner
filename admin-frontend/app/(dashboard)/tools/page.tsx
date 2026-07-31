"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  APIError,
  testConstraintResearch,
  testFestivalDiscovery,
  testRegionOverview
} from "../../../lib/api";
import { JsonPanel } from "../../components/shared";

export default function ToolsTesterPage() {
  const [tool, setTool] = useState<"regionOverview" | "constraintResearch" | "festivalDiscovery">("regionOverview");
  const [inputJson, setInputJson] = useState("{\n  \n}");
  const [output, setOutput] = useState<unknown | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleUnauthorized = () => {
    router.push("/login");
  };

  const TOOLS = [
    { id: "regionOverview", name: "Region Overview", desc: "Thống kê danh mục, giá cả và đánh giá." },
    { id: "constraintResearch", name: "Constraint Research", desc: "Phân tích khoảng cách, ngân sách và phân vùng." },
    { id: "festivalDiscovery", name: "Festival Discovery", desc: "Khám phá lễ hội theo tháng và khu vực." }
  ] as const;

  const currentTool = TOOLS.find(t => t.id === tool);

  async function runTest() {
    setError("");
    setOutput(null);
    setLoading(true);
    let payload;
    try {
      payload = JSON.parse(inputJson);
    } catch (e) {
      setError("JSON không hợp lệ. Vui lòng kiểm tra lại cú pháp.");
      setLoading(false);
      return;
    }

    try {
      let res;
      if (tool === "regionOverview") res = await testRegionOverview(payload);
      else if (tool === "constraintResearch") res = await testConstraintResearch(payload);
      else if (tool === "festivalDiscovery") res = await testFestivalDiscovery(payload);
      setOutput(res);
    } catch (caught) {
      if (caught instanceof APIError && caught.status === 401) {
        handleUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : "Có lỗi xảy ra khi gọi API.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="goldenSection" id="tools">
      <header>
        <div>
          <p className="eyebrow">Backend Research Tools</p>
          <h2>Tools Tester</h2>
          <p>Chạy thử và gỡ lỗi trực tiếp các tool lấy dữ liệu đầu vào cho AI Planner.</p>
        </div>
      </header>
      <div className="goldenLayout">
        <div className="goldenList">
          {TOOLS.map((item) => (
            <button
              type="button"
              key={item.id}
              onClick={() => { setTool(item.id as any); setOutput(null); setError(""); }}
              className={tool === item.id ? "active" : ""}
            >
              <span className="goldenCaseMeta">
                <em>{item.id}</em>
              </span>
              <b>{item.name}</b>
              <small>{item.desc}</small>
            </button>
          ))}
        </div>
        <article className="goldenDetail">
          <div className="goldenTitle">
            <span>{currentTool?.id}</span>
            <div>
              <h3>{currentTool?.name}</h3>
              <p>{currentTool?.desc}</p>
            </div>
            <button
              type="button"
              className="runCaseButton"
              onClick={runTest}
              disabled={loading}
            >
              {loading ? "Đang chạy..." : "▶ Run Tool"}
            </button>
          </div>
          
          <div className="goldenCompare">
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <b style={{ marginBottom: '8px' }}>Input JSON</b>
              <textarea
                value={inputJson}
                onChange={(e) => setInputJson(e.target.value)}
                style={{
                  flex: 1,
                  minHeight: '200px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '13px',
                  padding: '12px',
                  backgroundColor: 'var(--surface-color, #1a1a1a)',
                  color: 'var(--text-color, #f1f1f1)',
                  border: '1px solid var(--border-color, #333)',
                  borderRadius: '6px',
                  resize: 'vertical',
                  outline: 'none'
                }}
                spellCheck={false}
              />
            </div>
            <div>
              <b style={{ marginBottom: '8px', display: 'block' }}>Output</b>
              {output ? (
                <JsonPanel value={output} />
              ) : (
                <div style={{
                  padding: '12px',
                  color: '#888',
                  fontStyle: 'italic',
                  fontSize: '13px',
                  border: '1px dashed var(--border-color, #333)',
                  borderRadius: '6px',
                  height: 'calc(100% - 28px)'
                }}>
                  Kết quả sẽ hiển thị ở đây sau khi chạy...
                </div>
              )}
            </div>
          </div>
          {error && <div className="runCaseError" style={{ marginTop: '16px' }}>{error}</div>}
        </article>
      </div>
    </section>
  );
}
