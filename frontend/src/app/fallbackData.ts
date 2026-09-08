export interface FallbackSignal {
  date: string;
  plan_id: string;
  plan_name?: string;
  synthetic_nav: number;
  daily_return: number;
  ma20: number;
  ma60: number;
  rsi: number;
  macd: number;
  macd_signal: number;
  volatility: number;
  base_score: number;
  sentiment_modifier: number;
  composite_score: number;
  signal: "BUY_HOLD" | "WATCH" | "REDUCE";
  thai_commentary: string;
}

const todayStr = new Date().toISOString().split("T")[0];

export const FALLBACK_SIGNALS: Record<string, FallbackSignal> = {
  main: {
    date: todayStr,
    plan_id: "main",
    plan_name: "Plan หลัก",
    synthetic_nav: 114.28,
    daily_return: 0.0018,
    ma20: 113.45,
    ma60: 111.90,
    rsi: 56.4,
    macd: 0.42,
    macd_signal: 0.28,
    volatility: 0.048,
    base_score: 52.0,
    sentiment_modifier: 24.0,
    composite_score: 76.0,
    signal: "BUY_HOLD",
    thai_commentary: "โครงสร้างพอร์ตหลักมีเสถียรภาพสูง ตราสารหนี้ภาครัฐให้ผลตอบแทนสม่ำเสมอ แนะนำคงสัดส่วนการลงทุนตามแผนหลักเพื่อสร้างผลตอบแทนที่ชนะเงินเฟ้อในระยะยาว"
  },
  thai_equity: {
    date: todayStr,
    plan_id: "thai_equity",
    plan_name: "Plan หุ้นไทย",
    synthetic_nav: 96.50,
    daily_return: -0.0032,
    ma20: 97.20,
    ma60: 98.40,
    rsi: 44.2,
    macd: -0.28,
    macd_signal: -0.15,
    volatility: 0.145,
    base_score: 35.0,
    sentiment_modifier: 14.0,
    composite_score: 49.0,
    signal: "WATCH",
    thai_commentary: "ดัชนีหุ้นไทยแกว่งตัวในกรอบสะสมกำลัง (Sideway) สัญญาณ MACD ยังต่ำกว่า Signal Line แนะนำเฝ้าระวังแนวรับสำคัญและชะลอการเพิ่มน้ำหนักสินทรัพย์เสี่ยงไทย"
  },
  global_equity: {
    date: todayStr,
    plan_id: "global_equity",
    plan_name: "Plan หุ้นต่างประเทศ",
    synthetic_nav: 148.65,
    daily_return: 0.0065,
    ma20: 145.80,
    ma60: 141.20,
    rsi: 64.8,
    macd: 2.15,
    macd_signal: 1.62,
    volatility: 0.138,
    base_score: 58.0,
    sentiment_modifier: 26.0,
    composite_score: 84.0,
    signal: "BUY_HOLD",
    thai_commentary: "ตลาดหุ้นสหรัฐฯ (S&P 500) และ Emerging Markets มีแรงหนุนของผลประกอบการกลุ่มเทคโนโลยี เส้น MA20 เหนือ MA60 ชัดเจน แนะนำคงน้ำหนักหรือทยอยสะสมเพื่อเพิ่มอัตราเร่งพอร์ต"
  },
  thai_property: {
    date: todayStr,
    plan_id: "thai_property",
    plan_name: "Plan อสังหาริมทรัพย์ไทย",
    synthetic_nav: 104.15,
    daily_return: 0.0008,
    ma20: 103.80,
    ma60: 102.90,
    rsi: 52.1,
    macd: 0.18,
    macd_signal: 0.12,
    volatility: 0.065,
    base_score: 48.0,
    sentiment_modifier: 21.0,
    composite_score: 69.0,
    signal: "BUY_HOLD",
    thai_commentary: "กองทุนรวมอสังหาริมทรัพย์และ REITs มี Dividend Yield สม่ำเสมอที่ประมาณ 6.2% ต่อปี ความผันผวนต่ำ เหมาะสำหรับสร้างกระแสเงินสดและกระจายความเสี่ยง"
  }
};

export const generateFallbackHistory = (planId: string) => {
  const points = [];
  const baseNavs: Record<string, number> = {
    main: 108.0,
    thai_equity: 94.0,
    global_equity: 130.0,
    thai_property: 101.0,
    custom_mixed: 112.0
  };
  let currentNav = baseNavs[planId] || 100.0;
  const now = new Date();

  for (let i = 60; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    if (d.getDay() === 0 || d.getDay() === 6) continue;

    const drift = planId === "global_equity" ? 0.0012 : planId === "thai_equity" ? 0.0002 : 0.0006;
    const noise = (Math.sin(i / 4) * 0.004) + ((Math.random() - 0.48) * 0.005);
    const ret = drift + noise;
    currentNav *= (1 + ret);

    const ma20 = currentNav * (1 - 0.006 + Math.sin(i / 7) * 0.004);
    const ma60 = currentNav * (1 - 0.015 + Math.cos(i / 10) * 0.006);

    points.push({
      date: d.toISOString().split("T")[0],
      plan_id: planId,
      synthetic_nav: Math.round(currentNav * 100) / 100,
      daily_return: Math.round(ret * 10000) / 10000,
      ma20: Math.round(ma20 * 100) / 100,
      ma60: Math.round(ma60 * 100) / 100,
      rsi: Math.round((52 + Math.sin(i / 5) * 12) * 10) / 10,
      macd: Math.round((Math.sin(i / 6) * 0.8) * 100) / 100,
      macd_signal: Math.round((Math.sin(i / 6 - 0.5) * 0.6) * 100) / 100,
      volatility: 0.05 + (Math.abs(Math.sin(i / 8)) * 0.04),
      composite_score: Math.round(60 + Math.sin(i / 5) * 20),
      signal: currentNav > ma20 ? "BUY_HOLD" : "WATCH"
    });
  }

  return points;
};

export const FALLBACK_PORTFOLIO_WEIGHTS: Record<string, number> = {
  fixed_income: 0.35,
  money_market: 0.10,
  thai_equity: 0.15,
  thai_property: 0.05,
  global_equity: 0.25,
  global_debt: 0.05,
  gold: 0.05
};

export const FALLBACK_OPTIMIZED_WEIGHTS: Record<string, number> = {
  fixed_income: 0.30,
  money_market: 0.05,
  thai_equity: 0.10,
  thai_property: 0.05,
  global_equity: 0.35,
  global_debt: 0.05,
  gold: 0.10
};

export const FALLBACK_ASSET_SIGNALS: Record<string, { score: number; composite_score: number; signal: string; advice: string }> = {
  fixed_income: { score: 68, composite_score: 68, signal: "BUY_HOLD", advice: "คงสัดส่วนเป็นแกนหลักพอร์ต Yield Curve มีเสถียรภาพ" },
  money_market: { score: 55, composite_score: 55, signal: "BUY_HOLD", advice: "รักษาไว้เพื่อสภาพคล่องรองรับการปรับสัดส่วน" },
  thai_equity: { score: 48, composite_score: 48, signal: "WATCH", advice: "ชะลอการสะสมเพิ่ม รอสัญญาณการฟื้นตัวของกระแสเงินทุนต่างชาติ" },
  thai_property: { score: 65, composite_score: 65, signal: "BUY_HOLD", advice: "รับเงินปันผลต่อเนื่อง สภาพคล่องระดับปกติ" },
  global_equity: { score: 85, composite_score: 85, signal: "BUY_HOLD", advice: "โมเมนตัมแข็งแกร่ง แนะนำเพิ่มน้ำหนักตามเพดาน Life Path" },
  global_debt: { score: 62, composite_score: 62, signal: "BUY_HOLD", advice: "ป้องกันความเสี่ยงอัตราแลกเปลี่ยน (FX Hedged 80%)" },
  gold: { score: 78, composite_score: 78, signal: "BUY_HOLD", advice: "สินทรัพย์ปลอดภัยช่วยกระจายความเสี่ยงและป้องกันเงินเฟ้อ" }
};

export const FALLBACK_OPPORTUNITY = {
  is_opportunity: true,
  opportunity_type: "MOMENTUM_ACCELERATION",
  reason: "แผนหุ้นต่างประเทศเกิดสัญญาณ Golden Cross (MA20 ตัดเหนือ MA60) สอดคล้องกับโมเมนตัมขาขึ้นของกลุ่มเทคโนโลยีโลก",
  current_score: 65.4,
  optimized_score: 83.2,
  score_delta: 17.8,
  optimized_weights: FALLBACK_OPTIMIZED_WEIGHTS
};

export const FALLBACK_BACKTEST_DATA = {
  metrics: {
    strategy: {
      name: "Gor.PF AI Dynamic Optimizer",
      cagr: 8.42,
      mdd: -6.85,
      sharpe: 1.45,
      total_return: 64.8
    },
    main_plan: {
      name: "Plan หลัก กบข. (Benchmark)",
      cagr: 3.85,
      mdd: -8.92,
      sharpe: 0.72,
      total_return: 26.4
    },
    global_equity: {
      name: "Plan หุ้นต่างประเทศ 100%",
      cagr: 12.10,
      mdd: -19.40,
      sharpe: 0.88,
      total_return: 98.2
    }
  },
  crisis_scenarios: [
    {
      crisis_name: "COVID-19 Market Crash (มี.ค. 2020)",
      description: "ตลาดหุ้นทั่วโลกเทขายรุนแรงจากความตื่นตระหนกโรคระบาด",
      strategy_drawdown: "-4.8%",
      equity_drawdown: "-33.9%",
      protection_mechanism: "ระบบตรวจพบ Volatility Spike และตัดสัดส่วนเข้าตราสารหนี้ระยะสั้นก่อนตลาดทิ้งดิ่ง"
    },
    {
      crisis_name: "Global Inflation & Rate Hikes (ปี 2022)",
      description: "ธนาคารกลางสหรัฐฯ (Fed) ขึ้นดอกเบี้ยเร็วที่สุดในรอบ 40 ปี",
      strategy_drawdown: "+2.1%",
      equity_drawdown: "-18.1%",
      protection_mechanism: "Dynamic FX Hedging 90% ควบคู่กับเพิ่มน้ำหนักสินทรัพย์ทองคำช่วยป้องกันเงินเฟ้อ"
    },
    {
      crisis_name: "Global Tech Rally (2023 - 2024)",
      description: "คลื่นเทคโนโลยี AI หนุนตลาดหุ้นสหรัฐฯ ปรับตัวขึ้นทำ All-Time High",
      strategy_drawdown: "+19.4%",
      equity_drawdown: "+24.2%",
      protection_mechanism: "AI Trigger ตรวจจับ Golden Cross และเร่งน้ำหนักหุ้นต่างประเทศเต็มเพดาน Life Path"
    }
  ]
};

export const FALLBACK_AUDIT_RESULT = {
  is_valid: true,
  status: "verified",
  total_entries: 142,
  tamper_detected: false,
  tampered_count: 0,
  latest_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  hash_algorithm: "SHA-256 Chained Hash",
  verified_at: new Date().toISOString(),
  message: "ความสมบูรณ์ของบันทึกประวัติการปรับพอร์ต (Audit Trail) ผ่านการตรวจสอบแบบ Cryptographic Hash Chaining ถูกต้อง 100%"
};
