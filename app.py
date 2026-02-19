import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re 
from streamlit_autorefresh import st_autorefresh
import pytz
import numpy as np # ✅ นำเข้า numpy สำหรับทำสมการแนวโน้ม (Trend Line)

# 60,000 มิลลิวินาที = 1 นาที
st_autorefresh(interval=30000, key="datarefresh")

# กำหนดเขตเวลาประเทศไทย
tz_th = pytz.timezone('Asia/Bangkok')
now_th = datetime.now(tz_th)

# --- 1. การเชื่อมต่อและระบบ Cache ---
@st.cache_data(ttl=30)
def fetch_data_from_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_info:
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)
        client = gspread.authorize(creds)
        
        spreadsheet = client.open("Project IOT")
        sheet = spreadsheet.get_worksheet(0)
        
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"❌ ระบบเชื่อมต่อมีปัญหา: {str(e)}")
        return pd.DataFrame()

# --- 2. จัดการข้อมูล ---
try:
    df_raw = fetch_data_from_sheets()
    df = df_raw.copy()

    # Clean ชื่อคอลัมน์
    df.columns = df.columns.str.strip()
    df.rename(columns={
        'Air Humid': 'AirHumid', 'Air Humidity': 'AirHumid', 
        'Soil Humid': 'SoilHumid', 'Soil Humidity': 'SoilHumid',
        'Light Lux': 'LightLux', 'Lux': 'LightLux',
        'Air Temp': 'AirTemp', 'Temp': 'AirTemp'
    }, inplace=True)

    if not df.empty:
        target_cols = ['AirTemp', 'AirHumid', 'LightLux', 'SoilHumid']
        for col in target_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace('%', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].ffill().fillna(0)

    # แยกชุดข้อมูล (ลด df_predict ให้แคบลงเพื่อให้เทรนด์เส้นประไวต่อการเปลี่ยนแปลงล่าสุด)
    df_graph = df.tail(2000) if len(df) > 2000 else df
    df_predict = df.tail(300) if len(df) > 300 else df

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
    df = pd.DataFrame() 

# --- 3. หน้าจอ Dashboard ---
st.set_page_config(page_title="Morning Glory AI - Pro", layout="wide")

# CSS สำหรับกล่อง Status และ UI
st.markdown("""
    <style>
        .main { background-color: #0E1117; color: #FFFFFF; }
        .stMetric { background-color: #1E2129; padding: 15px; border-radius: 10px; border: 1px solid #31333F; }
        div[data-testid="metric-container"] { color: #FFFFFF; }
        
        .status-container { display: flex; justify-content: flex-end; gap: 15px; align-items: flex-start; padding-top: 15px; }
        .status-box { background-color: #1E2129; padding: 15px 20px; border-radius: 10px; border: 1px solid #31333F; text-align: right; min-width: 180px; height: 110px; display: flex; flex-direction: column; justify-content: center; }
        .status-label { font-size: 0.9em; color: #A0AEC0; display: block; margin-bottom: 2px;}
        .status-value { font-size: 1.5em; font-weight: bold; line-height: 1;}
        .status-time { font-size: 0.75em; color: #888888; display: block; margin-top: 8px; min-height: 1em; }
    </style>
    """, unsafe_allow_html=True)

if not df.empty:
    last_row = df.iloc[-1]
    
    current_fan = str(last_row.get('Fan', 'N/A')).strip().upper()
    current_pump = str(last_row.get('Pump', 'N/A')).strip().upper()
    
    last_pump_time = "ยังไม่พบข้อมูล"
    if 'Pump' in df.columns and 'Timestamp' in df.columns:
        df_pump_on = df[df['Pump'].astype(str).str.strip().str.upper() == 'ON']
        if not df_pump_on.empty:
            last_pump_time = str(df_pump_on.iloc[-1]['Timestamp'])
            last_pump_time = last_pump_time.replace("/2026", "").replace("/2025", "").replace("/2024", "")

    header_col1, header_col2 = st.columns([2.5, 2])
    
    with header_col1:
        st.title("🌱 Morning Glory Smart Dashboard")
        st.caption(f"🔄 อัปเดตข้อมูลล่าสุดเมื่อ: {now_th.strftime('%H:%M:%S')} น. (รีเฟรชทุก 30 วินาที)")
        
    with header_col2:
        fan_color = "#00D4FF" if current_fan == "MAX" else "#FFD700" 
        pump_color = "#00FF7F" if current_pump == "ON" else "#FF4B4B" 
        st.markdown(f"""
            <div class="status-container">
                <div class="status-box">
                    <span class="status-label">พัดลม (Fan)</span>
                    <span class="status-value" style="color: {fan_color};">{current_fan}</span>
                    <span class="status-time"></span> 
                </div>
                <div class="status-box">
                    <span class="status-label">ปั๊มน้ำ (Pump)</span>
                    <span class="status-value" style="color: {pump_color};">{current_pump}</span>
                    <span class="status-time">ทำงานล่าสุด: {last_pump_time}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # ส่วนแสดงข้อมูลสรุปด้านบน
    st.subheader(f"📅 วันที่ปลูก: วันที่ {last_row.get('Day', '?')}")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🌡️ อุณหภูมิ", f"{last_row.get('AirTemp', 0):.2f} °C")
    col2.metric("💧 ความชื้นอากาศ", f"{last_row.get('AirHumid', 0):.2f}%")
    col3.metric("☀️ แสงสว่าง", f"{last_row.get('LightLux', 0):.2f} lx")
    col4.metric("🪴 ความชื้นดิน", f"{last_row.get('SoilHumid', 0):.2f}%")

    st.divider()

    # --- ส่วนของกราฟ Interactive ---
    st.subheader("📊 กราฟวิเคราะห์แนวโน้ม")
    
    option = st.radio(
        "เลือกดูข้อมูลที่ต้องการ:",
        ('ทั้งหมด', 'อุณหภูมิ', 'ความชื้นอากาศ', 'แสงสว่าง', 'ความชื้นดิน'),
        horizontal=True
    )

    def create_plot(selected_option):
        fig = go.Figure()
        
        metrics = {
            'อุณหภูมิ': {'col': 'AirTemp', 'color': '#FF4B4B', 'label': 'ค่าอุณหภูมิในอากาศ (°C)'},
            'ความชื้นอากาศ': {'col': 'AirHumid', 'color': '#00D4FF', 'label': 'ค่าความชื้นในอากาศ (%)'},
            'แสงสว่าง': {'col': 'LightLux', 'color': '#FFD700', 'label': 'ค่าความเข้มแสงสว่าง (lx)'},
            'ความชื้นดิน': {'col': 'SoilHumid', 'color': '#00FF7F', 'label': 'ค่าความชื้นในดิน (%)'}
        }

        if 'Timestamp' in df_graph.columns:
            x_axis = df_graph['Timestamp']
        else:
            x_axis = df_graph.index 

        if selected_option == 'ทั้งหมด':
            for name, m in metrics.items():
                if m['col'] in df_graph.columns:
                    fig.add_trace(go.Scatter(x=x_axis, y=df_graph[m['col']], mode='lines', name=name, line=dict(color=m['color'])))
            y_label = "สรุปเซนเซอร์ทั้งหมด"
        else:
            m = metrics[selected_option]
            if m['col'] in df_graph.columns:
                actual_data = df_graph[m['col']].tolist()
                y_label = m['label']
                
                fig.add_trace(go.Scatter(
                    x=x_axis, y=actual_data, mode='lines', 
                    name=f'ข้อมูล {selected_option}', line=dict(color=m['color'], width=2)
                ))
                
                # ✅ ปรับปรุง Predict Logic เป็น Linear Regression (หาความชันจริง)
                if m['col'] in df_predict.columns:
                    try:
                        series_predict = df_predict[m['col']].dropna()
                        if len(series_predict) > 10:
                            x_idx = np.arange(len(series_predict))
                            fit = np.polyfit(x_idx, series_predict.values, 1) # สร้างสมการเส้นตรง
                            trend_line = np.poly1d(fit)
                            
                            last_idx = x_idx[-1]
                            predict_values = [actual_data[-1]]
                            
                            # คำนวณค่าล่วงหน้า 36 จุด (6 ชม.)
                            for i in range(1, 37):
                                next_val = trend_line(last_idx + i)
                                # ป้องกันค่าเกินความเป็นจริง
                                if 'Humid' in m['col']: next_val = max(0, min(100, next_val))
                                if 'Lux' in m['col']: next_val = max(0, next_val)
                                predict_values.append(next_val)
                                
                            last_time = datetime.strptime(str(x_axis.iloc[-1]), "%d/%m/%Y, %H:%M:%S")
                            predict_times = [x_axis.iloc[-1]]
                            for i in range(1, 37):
                                next_time = last_time + timedelta(minutes=10 * i)
                                predict_times.append(next_time.strftime("%d/%m/%Y, %H:%M:%S"))

                            fig.add_trace(go.Scatter(
                                x=predict_times, y=predict_values, mode='lines', 
                                name='แนวโน้ม (Trend 6 ชม.)',
                                line=dict(color='white', width=2, dash='dot')
                            ))
                    except:
                        pass

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="white"),
            xaxis=dict(title="เวลา (Timestamp)", gridcolor='#31333F', showgrid=True, nticks=10),
            yaxis=dict(title=y_label, gridcolor='#31333F', showgrid=True),
            hovermode="x unified", template="plotly_dark",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        return fig

    st.plotly_chart(create_plot(option), use_container_width=True)

    # --- ✅ ส่วนของระบบพยากรณ์ความเสี่ยงโรคพืชและความเครียด (Environmental AI) ---
    st.divider()
    st.subheader("🛡️ ระบบประเมินความเสี่ยงและสุขภาพพืช (Plant Health & Risk AI)")
    
    # ดึงค่าล่าสุดเพื่อประเมิน
    cur_temp = last_row.get('AirTemp', 0)
    cur_humid = last_row.get('AirHumid', 0)
    cur_soil = last_row.get('SoilHumid', 0)
    cur_light = last_row.get('LightLux', 0)

    # -- Logic 1: ประเมินเชื้อราและโรคโคนเน่า (Damping-off) --
    if cur_temp > 30 and cur_humid > 80:
        mold_stat = "🔴 เสี่ยงสูงมาก (High Risk)"
        mold_desc = "อากาศร้อนชื้นจัด เสี่ยงเกิดโรคโคนเน่า/เชื้อรา แนะนำให้พัดลมทำงานที่ระดับ MAX เพื่อระบายอากาศด่วน"
        mold_color = "error"
    elif cur_temp > 28 and cur_humid > 75:
        mold_stat = "🟡 เฝ้าระวัง (Warning)"
        mold_desc = "อากาศเริ่มอบอ้าว ควรรักษาการถ่ายเทอากาศให้ดีเพื่อป้องกันเชื้อราสะสม"
        mold_color = "warning"
    else:
        mold_stat = "🟢 ปลอดภัย (Safe)"
        mold_desc = "สภาพอากาศถ่ายเทดี ระดับความต้านทานโรคของพืชอยู่ในเกณฑ์ปกติ"
        mold_color = "success"

    # -- Logic 2: ประเมินความเครียดจากความร้อน/แสง (Heat & Light Stress) --
    if cur_temp > 33 and cur_light > 2000:
        stress_stat = "🔴 พืชเครียดจัด (Severe Stress)"
        stress_desc = "แดดแรงและอากาศร้อนจัด ระวังใบไหม้ ต้นอ่อนอาจเหี่ยวเฉา ควรพรางแสงหรือฉีดพ่นละอองน้ำ"
        stress_color = "error"
    elif cur_temp > 31 and cur_soil < 50:
        stress_stat = "🟡 เสี่ยงขาดน้ำ (Water Stress)"
        stress_desc = "อากาศร้อนแต่ดินเริ่มแห้ง พืชอาจสูญเสียน้ำเร็วกว่าที่ดูดซึมได้"
        stress_color = "warning"
    else:
        stress_stat = "🟢 สภาพปกติ (Optimal)"
        stress_desc = "พืชสามารถสังเคราะห์แสงและคายน้ำได้อย่างมีประสิทธิภาพ"
        stress_color = "success"

    # -- Logic 3: ประเมินสุขภาพดินและการรดน้ำ --
    if cur_soil < 40:
        soil_stat = "🔴 ดินแห้งเกินไป"
        soil_desc = "ควรรดน้ำทันทีเพื่อป้องกันรากแห้งตาย"
        soil_color = "error"
    elif cur_soil > 85:
        soil_stat = "🟡 ดินแฉะเกินไป"
        soil_desc = "ดินอุ้มน้ำมากเกินไประวังรากขาดออกซิเจน"
        soil_color = "warning"
    else:
        soil_stat = "🟢 ดินชุ่มชื้นพอดี"
        soil_desc = "ระดับความชื้นเหมาะสมต่อการดูดซึมธาตุอาหาร"
        soil_color = "success"

    # แสดงผล UI ออกหน้าจอ
    col_risk1, col_risk2 = st.columns(2)
    
    with col_risk1:
        st.markdown(f"#### 🦠 ความเสี่ยงโรคราคอดิน (Mold Risk)")
        if mold_color == "error": st.error(f"**{mold_stat}**: {mold_desc}")
        elif mold_color == "warning": st.warning(f"**{mold_stat}**: {mold_desc}")
        else: st.success(f"**{mold_stat}**: {mold_desc}")
        
        st.markdown("---")
        st.markdown(f"#### ☀️ ความเครียดจากสภาพแวดล้อม (Plant Stress)")
        if stress_color == "error": st.error(f"**{stress_stat}**: {stress_desc}")
        elif stress_color == "warning": st.warning(f"**{stress_stat}**: {stress_desc}")
        else: st.success(f"**{stress_stat}**: {stress_desc}")

    with col_risk2:
        st.markdown(f"#### 🪴 สถานะความชื้นในดิน (Soil Status)")
        if soil_color == "error": st.error(f"**{soil_stat}**: {soil_desc}")
        elif soil_color == "warning": st.warning(f"**{soil_stat}**: {soil_desc}")
        else: st.success(f"**{soil_stat}**: {soil_desc}")

        st.markdown("---")
        # แสดงสูตรวิเคราะห์สภาพแวดล้อมภาพรวม (Overall Score)
        env_score = 100
        if cur_temp > 30 or cur_temp < 24: env_score -= 15
        if cur_humid > 80 or cur_humid < 50: env_score -= 15
        if cur_soil < 50 or cur_soil > 85: env_score -= 20
        
        st.metric("🏆 คะแนนความเหมาะสมสภาพแวดล้อม (Overall Score)", f"{env_score}/100")
        st.caption("อิงจากค่า Temperature, Humidity และ Soil Moisture ที่เหมาะสมต่อต้นอ่อนผักบุ้ง")

else:
    st.warning("🌙 ไม่พบข้อมูลในระบบ กำลังรอสัญญาณจาก ESP32...")