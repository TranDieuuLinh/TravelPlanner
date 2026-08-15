"use client";

import "@/styles/global/landing.css";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/features/auth/components/AuthProvider";
import { searchListings } from "@/features/marketplace/api";
import type { ListingSummary } from "@/features/marketplace/types";

function ArrowIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M4 12h15m-6-6 6 6-6 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

function LinkIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M10.5 13.5 13.5 10.5M8.2 16.8l-1.1 1.1a3.6 3.6 0 0 1-5-5l3.1-3.1a3.6 3.6 0 0 1 5-0.1M15.8 7.2l1.1-1.1a3.6 3.6 0 0 1 5 5l-3.1 3.1a3.6 3.6 0 0 1-5 .1" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

function RouteIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <circle cx="6" cy="6" r="2.5" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="18" cy="18" r="2.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8.5 6h2.2a4 4 0 0 1 4 4v4a4 4 0 0 0 4 4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="m5 12.5 4.2 4.2L19 7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
      <path d="M12 3 19 6v5.2c0 4.5-2.9 7.6-7 9.8-4.1-2.2-7-5.3-7-9.8V6l7-3Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
      <path d="m8.5 12 2.2 2.2 4.8-4.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

function formatPrice(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat("vi-VN", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${amount.toLocaleString("vi-VN")} ${currency}`;
  }
}

function listingCover(listing: ListingSummary) {
  return listing.currentVersion.mediaUrls?.[0] || "/images/planner-vietnam-thoughts.png";
}

function ProductPreview() {
  const previewRef = useRef<HTMLDivElement>(null);
  const animationFrameRef = useRef<number | null>(null);
  const pendingTiltRef = useRef({ x: 0, y: 0 });

  useEffect(() => () => {
    if (animationFrameRef.current !== null) window.cancelAnimationFrame(animationFrameRef.current);
  }, []);

  function updatePreviewTilt(event: React.PointerEvent<HTMLDivElement>) {
    if (event.pointerType !== "mouse" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    pendingTiltRef.current = {
      x: ((event.clientX - bounds.left) / bounds.width - .5) * 2,
      y: ((event.clientY - bounds.top) / bounds.height - .5) * 2,
    };
    if (animationFrameRef.current !== null) return;
    animationFrameRef.current = window.requestAnimationFrame(() => {
      const element = previewRef.current;
      if (element) {
        const { x, y } = pendingTiltRef.current;
        element.style.setProperty("--preview-rotate-x", `${(-y * 3.5).toFixed(2)}deg`);
        element.style.setProperty("--preview-rotate-y", `${(x * 5).toFixed(2)}deg`);
        element.style.setProperty("--preview-shift-x", `${(x * 7).toFixed(2)}px`);
        element.style.setProperty("--preview-shift-y", `${(y * 5).toFixed(2)}px`);
        element.style.setProperty("--preview-counter-x", `${(-x * 4).toFixed(2)}px`);
        element.style.setProperty("--preview-counter-y", `${(-y * 3).toFixed(2)}px`);
      }
      animationFrameRef.current = null;
    });
  }

  function resetPreviewTilt() {
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    const element = previewRef.current;
    if (!element) return;
    element.style.setProperty("--preview-rotate-x", "0deg");
    element.style.setProperty("--preview-rotate-y", "0deg");
    element.style.setProperty("--preview-shift-x", "0px");
    element.style.setProperty("--preview-shift-y", "0px");
    element.style.setProperty("--preview-counter-x", "0px");
    element.style.setProperty("--preview-counter-y", "0px");
  }

  return (
    <div
      aria-label="Bản xem trước quy trình tạo kế hoạch của TravelPlanner"
      className="landingProductPreview"
      onPointerCancel={resetPreviewTilt}
      onPointerLeave={resetPreviewTilt}
      onPointerMove={updatePreviewTilt}
      ref={previewRef}
    >
      <div className="landingPreviewGlow" />
      <div className="landingPreviewMap" aria-hidden="true">
        <span className="landingMapWater landingMapWaterOne" />
        <span className="landingMapWater landingMapWaterTwo" />
        <span className="landingMapRoad landingMapRoadOne" />
        <span className="landingMapRoad landingMapRoadTwo" />
        <span className="landingMapRoad landingMapRoadThree" />
        <svg className="landingPreviewRoute" fill="none" viewBox="0 0 480 340">
          <path d="M100 74c57 24 74 72 120 91 38 16 44-7 82 17 30 19 37 56 75 82" stroke="#325fba" strokeLinecap="round" strokeWidth="7" />
          <path d="M100 74c57 24 74 72 120 91 38 16 44-7 82 17 30 19 37 56 75 82" stroke="#8eb4ff" strokeLinecap="round" strokeWidth="2" />
        </svg>
        <span className="landingMapPin landingMapPinStart">A</span>
        <span className="landingMapPin landingMapPinEnd">B</span>
      </div>
      <Image
        alt="Các nhân vật TravelPlanner khám phá những điểm đến Việt Nam"
        className="landingHeroCrew"
        height={640}
        priority
        src="/images/explorer-crew-vietnam-v2-transparent.png"
        width={900}
      />
      <div className="landingPreviewSourceCard">
        <span className="landingPreviewEyebrow"><LinkIcon /> Nguồn cảm hứng</span>
        <strong>Video du lịch Hà Nội</strong>
        <span className="landingSourceLine">Địa điểm sẽ được giữ lại sau khi bạn xác nhận</span>
      </div>
      <div className="landingPreviewPlanCard">
        <div className="landingPlanCardHeader">
          <div>
            <span className="landingPreviewEyebrow">Lịch trình cá nhân</span>
            <strong>Hà Nội · 3 ngày</strong>
          </div>
          <span className="landingPlanStatus"><CheckIcon /> Sẵn sàng</span>
        </div>
        <div className="landingPlanDay active">
          <span className="landingDayNumber">01</span>
          <div><strong>Phố cũ & văn hóa địa phương</strong><small>3 điểm · 2 chặng di chuyển</small></div>
        </div>
        <div className="landingPlanDay">
          <span className="landingDayNumber">02</span>
          <div><strong>Cà phê & không gian xanh</strong><small>Nhịp độ thong thả</small></div>
        </div>
      </div>
      <div className="landingPreviewAssistant">
        <Image alt="Trợ lý TravelPlanner" height={72} src="/images/penguin-plan.png" width={52} />
        <span>Giữ lại các điểm bạn thích,<br />mình sẽ xếp lại tuyến.</span>
      </div>
    </div>
  );
}

function StepCard({ number, icon, title, description }: { number: string; icon: React.ReactNode; title: string; description: string }) {
  return (
    <article className="landingStepCard">
      <div className="landingStepTop"><span className="landingStepIcon">{icon}</span><span className="landingStepNumber">{number}</span></div>
      <h3>{title}</h3>
      <p>{description}</p>
    </article>
  );
}

function FeatureRow({ children }: { children: React.ReactNode }) {
  return <li><span className="landingFeatureCheck"><CheckIcon /></span><span>{children}</span></li>;
}

export default function HomePage() {
  const { user } = useAuth();
  const [featuredListings, setFeaturedListings] = useState<ListingSummary[]>([]);
  const [listingsLoading, setListingsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void searchListings({ page: 1, pageSize: 3, sort: "newest" })
      .then((result) => {
        if (!cancelled) setFeaturedListings(result.items);
      })
      .catch(() => {
        if (!cancelled) setFeaturedListings([]);
      })
      .finally(() => {
        if (!cancelled) setListingsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const plannerHref = user ? "/planner" : "/login?next=%2Fplanner";

  return (
    <main className="landingPage">
      <section className="landingHero pageWidth">
        <div className="landingHeroCopy">
          <span className="landingKicker"><span className="landingKickerDot" /> Lập kế hoạch du lịch cùng AI</span>
          <h1><span>Ý tưởng thành</span><br />hành trình.</h1>
          <p className="landingHeroLead">Dán một video hoặc kể điều bạn thích. TravelPlanner giúp bạn gom địa điểm, xếp tuyến và tạo một lịch trình vừa với cách bạn muốn đi.</p>
          <div className="landingHeroActions">
            <Link className="landingButton landingButtonPrimary" href={plannerHref}>Lên lịch trình của tôi <ArrowIcon /></Link>
            <a className="landingButton landingButtonQuiet" href="#how-it-works">Xem TravelPlanner hoạt động</a>
          </div>
          <div className="landingHeroSignals" aria-label="Các lợi ích chính">
            <span><ShieldIcon /> Nguồn rõ ràng</span>
            <span><RouteIcon /> Tuyến dễ theo dõi</span>
            <span><CheckIcon /> Chỉnh sửa linh hoạt</span>
          </div>
        </div>
        <ProductPreview />
      </section>

      <section className="landingValueStrip" aria-label="Chuỗi giá trị của TravelPlanner">
        <div className="pageWidth landingValueInner">
          <span>Video và ý tưởng</span><i>→</i><span>Địa điểm đã xác nhận</span><i>→</i><span>Lộ trình phù hợp</span><i>→</i><strong>Plan của bạn</strong>
        </div>
      </section>

      <section className="landingSection pageWidth" id="how-it-works">
        <div className="landingSectionIntro">
          <span className="landingKicker">Cách hoạt động</span>
          <h2>Bắt đầu nhẹ nhàng. Đi với một plan rõ ràng.</h2>
          <p>Không cần điền một form dài. Bạn chia sẻ ý tưởng, TravelPlanner làm rõ phần còn thiếu và để bạn quyết định những điểm thực sự quan trọng.</p>
        </div>
        <div className="landingStepsGrid">
          <StepCard number="01" icon={<LinkIcon />} title="Đưa cảm hứng vào" description="Dán URL video, nội dung tham khảo hoặc bắt đầu bằng một yêu cầu tự nhiên." />
          <StepCard number="02" icon={<ShieldIcon />} title="Xác nhận điều quan trọng" description="Xem các địa điểm được tìm thấy, giữ lại nơi bạn muốn và bỏ qua kết quả chưa chắc chắn." />
          <StepCard number="03" icon={<RouteIcon />} title="Nhận lịch trình dễ theo" description="Các điểm được xếp theo ngày, nhịp độ, tuyến đường, bữa ăn và những ràng buộc của nhóm." />
        </div>
      </section>

      <section className="landingSection landingProofSection pageWidth">
        <div className="landingProofVisual">
          <div className="landingChatBubble landingChatBubbleUser">Tôi muốn đi Hà Nội 3 ngày, thích văn hóa, cà phê và đi thong thả.</div>
          <div className="landingChatBubble landingChatBubbleAssistant"><Image alt="Trợ lý TravelPlanner" height={44} src="/images/penguin-chat.png" width={38} /><span><strong>Đã hiểu</strong><br />Hà Nội · 3 ngày · Văn hóa · Cà phê · Nhịp độ thong thả</span></div>
          <div className="landingPreferenceChips"><span>Hà Nội</span><span>3 ngày</span><span>Văn hóa</span><span>Đi thong thả</span></div>
        </div>
        <div className="landingProofCopy">
          <span className="landingKicker">Kể theo cách của bạn</span>
          <h2>Một câu nói tự nhiên cũng đủ để bắt đầu.</h2>
          <p>Explorer gom điểm đến, số ngày, nhóm đi, ngân sách, sở thích và ràng buộc thành một brief rõ ràng trước khi Planner xếp lịch.</p>
          <ul className="landingFeatureList">
            <FeatureRow>Không phải trả lời hàng chục câu hỏi ngay từ đầu</FeatureRow>
            <FeatureRow>Thông tin đã hiểu luôn hiện để bạn chỉnh nhanh</FeatureRow>
            <FeatureRow>Thiếu dữ liệu quan trọng sẽ được hỏi đúng lúc</FeatureRow>
          </ul>
        </div>
      </section>

      <section className="landingSection landingPlansSection pageWidth">
        <div className="landingSectionIntro landingSectionIntroCentered">
          <span className="landingKicker">Một chuyến đi, nhiều phương án</span>
          <h2>Một chuyến đi luôn cần chỗ để thay đổi.</h2>
          <p>Bạn có thể xem cảnh báo, giữ lại điểm quan trọng và tiếp tục chỉnh sửa mà không phải làm lại từ đầu.</p>
        </div>
        <div className="landingPlanOptions">
          <article><span className="landingOptionIcon main"><RouteIcon /></span><h3>Lịch trình chính</h3><p>Tuyến chính được xếp theo thời gian, sở thích và các điểm đã xác nhận.</p><span className="landingOptionNote">Theo ngày và tuyến đường</span></article>
          <article><span className="landingOptionIcon backup"><ShieldIcon /></span><h3>Phương án dự phòng</h3><p>Một plan riêng khi thời tiết, giờ mở cửa hoặc tuyến đường thay đổi.</p><span className="landingOptionNote">Không ghi đè plan chính</span></article>
          <article><span className="landingOptionIcon edit"><CheckIcon /></span><h3>Chỉnh sửa linh hoạt</h3><p>Thêm, xóa, đổi ngày hoặc yêu cầu AI điều chỉnh đúng phạm vi bạn muốn.</p><span className="landingOptionNote">Giữ nguyên điểm đã khóa</span></article>
        </div>
        <div className="landingPlansAction"><Link className="landingButton landingButtonPrimary" href={plannerHref}>Thử lên lịch trình <ArrowIcon /></Link></div>
      </section>

      <section className="landingMarketplaceSection pageWidth" id="explore">
        <div className="landingMarketplaceCopy">
          <span className="landingKicker">Khám phá cùng creator</span>
          <h2>Không muốn bắt đầu từ trang trắng?</h2>
          <p>Xem những hành trình được chia sẻ bởi creator, lấy cảm hứng và tiếp tục tùy chỉnh theo chuyến đi của bạn.</p>
          <Link className="landingButton landingButtonSecondary" href="/explore">Xem plan từ cộng đồng <ArrowIcon /></Link>
        </div>
        <div className="landingFeaturedListings" aria-live="polite">
          {listingsLoading ? [0, 1, 2].map((item) => <div className="landingListingSkeleton" key={item} />) : featuredListings.length ? featuredListings.map((listing) => {
            const version = listing.currentVersion;
            return <Link className="landingListingCard" href={`/listings/${listing.id}`} key={listing.id}>
              <div className="landingListingImage"><img alt={version.title} loading="lazy" src={listingCover(listing)} /><span>{version.durationDays} ngày</span></div>
              <div className="landingListingBody"><strong>{version.title}</strong><span>{version.destination} · {formatPrice(version.priceAmount, version.priceCurrency)}</span></div>
            </Link>;
          }) : <div className="landingListingsEmpty"><strong>Những hành trình mới đang được chuẩn bị.</strong><span>Trong lúc chờ, bạn có thể bắt đầu tạo plan riêng từ một điểm đến hoặc URL.</span></div>}
        </div>
      </section>

      <section className="landingCreatorSection pageWidth" id="for-creators">
        <div className="landingCreatorVisual"><Image alt="Chim cánh cụt TravelPlanner đang chuẩn bị kế hoạch" height={320} src="/images/penguin-plan.png" width={230} /></div>
        <div className="landingCreatorCopy"><span className="landingKicker">Dành cho creator</span><h2>Biến trải nghiệm địa phương thành một hành trình có cấu trúc.</h2><p>Bắt đầu từ video, tuyến đường hoặc plan bạn đã có. Bổ sung ngữ cảnh, nguồn và cách kể của riêng bạn để chia sẻ với cộng đồng.</p><Link className="landingTextLink" href={user ? "/creator/listings/new" : "/login?next=%2Fcreator%2Flistings%2Fnew"}>Khám phá Creator Studio <ArrowIcon /></Link></div>
      </section>

      <section className="landingFaqSection pageWidth">
        <div className="landingSectionIntro"><span className="landingKicker">Câu hỏi thường gặp</span><h2>Bắt đầu nhẹ nhàng, chỉnh sửa bất cứ lúc nào.</h2></div>
        <div className="landingFaqList">
          <details><summary>Tôi có cần biết chính xác mọi địa điểm trước không?</summary><p>Không. Bạn có thể bắt đầu bằng điểm đến, một yêu cầu tự nhiên hoặc URL. Những địa điểm chưa đủ chắc chắn sẽ được giữ riêng để bạn xác nhận.</p></details>
          <details><summary>Tôi có thể thay đổi lịch trình sau khi tạo không?</summary><p>Có. Bạn có thể chỉnh từng item hoặc yêu cầu Planner điều chỉnh một ngày, một khung giờ hay các điểm chưa khóa.</p></details>
          <details><summary>Tôi có cần đăng nhập không?</summary><p>Bạn có thể xem landing page và khám phá nội dung công khai. Để tạo và lưu plan, bạn cần đăng nhập để lịch trình được gắn với tài khoản.</p></details>
        </div>
      </section>

      <section className="landingFinalCta pageWidth">
        <div><span className="landingKicker">Sẵn sàng lên đường?</span><h2>Một video bạn lưu lại có thể là điểm bắt đầu.</h2></div>
        <Link className="landingButton landingButtonPrimary" href={plannerHref}>Bắt đầu với chuyến đi của tôi <ArrowIcon /></Link>
      </section>
    </main>
  );
}
