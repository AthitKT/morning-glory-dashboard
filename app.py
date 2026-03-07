import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.graph_objects as go
from plotly.subplots import make_subplots 
from datetime import datetime, timedelta
import re 
from streamlit_autorefresh import st_autorefresh
import pytz
import numpy as np 

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

    # แยกชุดข้อมูล 
    df_graph = df.tail(2000) if len(df) > 2000 else df
    df_predict = df.tail(300) if len(df) > 300 else df

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
    df = pd.DataFrame() 

# --- 3. หน้าจอ Dashboard ---
st.set_page_config(page_title="Morning Glory Dashboard", layout="wide")

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
    
    # ✅ ดึงค่าและคำนวณ PPFD ไว้ล่วงหน้า
    cur_temp = last_row.get('AirTemp', 0)
    cur_humid = last_row.get('AirHumid', 0)
    cur_soil = last_row.get('SoilHumid', 0)
    cur_light = last_row.get('LightLux', 0)
    cur_ppfd = cur_light * 0.065 # ตัวคูณแปลง Lux ผนัง -> PPFD กลางแปลง
    
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
        st.caption(f"🔄 อัปเดตข้อมูลล่าสุดเมื่อ: {now_th.strftime('%H:%M:%S')} น. (อัปเดตทุก 30 วินาที)")
        
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
    col1.metric("🌡️ อุณหภูมิ", f"{cur_temp:.2f} °C")
    col2.metric("💧 ความชื้นอากาศ", f"{cur_humid:.2f}%")
    # ✅ แสดงค่า PPFD และใส่ Lux ไว้ใน tooltip (เอาเมาส์ชี้เพื่อดู)
    col3.metric("☀️ แสง (PPFD)", f"{cur_ppfd:.2f} µmol/m²/s", help=f"เซนเซอร์จับได้: {cur_light:.0f} lx")
    col4.metric("🪴 ความชื้นดิน", f"{cur_soil:.2f}%")

    st.divider()

    # --- ส่วนของกราฟ Interactive ---
    st.subheader("📊 กราฟวิเคราะห์แนวโน้ม")
    
    # 1. เพิ่มปุ่มกดเลือกข้อมูล (อันนี้สำคัญมากเพื่อให้ฟังก์ชัน create_plot ทำงานได้)
    option = st.radio(
        "เลือกดูข้อมูลที่ต้องการ:",
        ('ทั้งหมด', 'อุณหภูมิ', 'ความชื้นอากาศ', 'แสงสว่าง', 'ความชื้นดิน'),
        horizontal=True
    )

   # 2. ฟังก์ชันวาดกราฟ
    def create_plot(selected_option):
        fig = go.Figure()
        
        # ✅ อัปเดตคีย์ 'min_ok' และ 'max_ok' ตามที่ต้องการ
        metrics = {
            'อุณหภูมิ': {'col': 'AirTemp', 'color': '#FF4B4B', 'label': 'ค่าอุณหภูมิในอากาศ (°C)', 'min_ok': 24, 'max_ok': 31}, # อัปเดต max เป็น 31
            'ความชื้นอากาศ': {'col': 'AirHumid', 'color': '#00D4FF', 'label': 'ค่าความชื้นในอากาศ (%)', 'min_ok': 50, 'max_ok': 80},
            'แสงสว่าง': {'col': 'LightLux', 'color': '#FFD700', 'label': 'ค่าความเข้มแสงสว่าง (lx)', 'min_ok': 1000, 'max_ok': 3000},
            'ความชื้นดิน': {'col': 'SoilHumid', 'color': '#00FF7F', 'label': 'ค่าความชื้นในดิน (%)', 'min_ok': 40, 'max_ok': 80} # อัปเดต min=40, max=80
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
                
                # ✅ เพิ่มแถบสีเขียว (Optimal Range) เพื่อบอกช่วงค่าที่รับได้
                fig.add_hrect(
                    y0=m['min_ok'], y1=m['max_ok'], 
                    fillcolor="#00FF7F", opacity=0.1, # พื้นหลังสีเขียวใสๆ
                    line_width=1.5, line_dash="dash", line_color="#00FF7F", # เส้นประขอบบน-ล่าง
                    annotation_text="ช่วงที่เหมาะสม", annotation_position="top left",
                    annotation_font_color="#00FF7F", annotation_font_size=12
                )
                
                # วาดเส้นข้อมูลจริงทับลงไป
                fig.add_trace(go.Scatter(
                    x=x_axis, y=actual_data, mode='lines', 
                    name=f'ข้อมูล {selected_option}', line=dict(color=m['color'], width=2)
                ))
                
                # ส่วนของการพยากรณ์ (Trend)
                if m['col'] in df_predict.columns:
                    try:
                        series_predict = df_predict[m['col']].dropna()
                        if len(series_predict) > 10:
                            x_idx = np.arange(len(series_predict))
                            fit = np.polyfit(x_idx, series_predict.values, 1) 
                            trend_line = np.poly1d(fit)
                            
                            last_idx = x_idx[-1]
                            predict_values = [actual_data[-1]]
                            
                            last_time_str = str(x_axis.iloc[-1])
                            try:
                                last_time = datetime.strptime(last_time_str, "%d/%m/%Y, %H:%M:%S")
                            except ValueError:
                                last_time = datetime.strptime(last_time_str, "%d/%m/%Y, %H:%M")

                            predict_times = [x_axis.iloc[-1]]
                            
                            for i in range(1, 37):
                                next_time = last_time + timedelta(minutes=10 * i)
                                next_val = trend_line(last_idx + i)
                                
                                if 'Humid' in m['col']: 
                                    next_val = max(0, min(100, next_val))
                                
                                if 'Lux' in m['col']: 
                                    if next_time.hour >= 20 or next_time.hour < 6:
                                        next_val = 0
                                    else:
                                        next_val = max(0, next_val)
                                        
                                predict_values.append(next_val)
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

    # 3. สั่งวาดกราฟออกมาโชว์
    st.plotly_chart(create_plot(option), use_container_width=True)
    

    # --- ส่วนของกราฟเปรียบเทียบ (Dual-Axis Chart) ---
    st.divider()
    st.subheader("⚖️ วิเคราะห์สมดุลอากาศ (Temp vs Humid Comparison)")
    st.caption("ดูกราฟนี้เพื่อเฝ้าระวังเชื้อรา: หากเส้นอุณหภูมิ(แดง) และความชื้น(ฟ้า) พุ่งสูงขึ้นพร้อมกัน จะเป็นจุดวิกฤตที่เชื้อราเติบโตได้ดี")
    
    if 'Timestamp' in df_graph.columns and 'AirTemp' in df_graph.columns and 'AirHumid' in df_graph.columns:
        fig_dual = make_subplots(specs=[[{"secondary_y": True}]])
        
        x_axis_dual = df_graph['Timestamp']
        
        fig_dual.add_trace(go.Scatter(x=x_axis_dual, y=df_graph['AirTemp'], name="อุณหภูมิ (°C)", line=dict(color='#FF4B4B', width=2)), secondary_y=False)
        fig_dual.add_trace(go.Scatter(x=x_axis_dual, y=df_graph['AirHumid'], name="ความชื้นอากาศ (%)", line=dict(color='#00D4FF', width=2, dash='dot')), secondary_y=True)

        fig_dual.update_layout(
            template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            hovermode="x unified", height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=20, r=20, t=30, b=20)
        )
        fig_dual.update_yaxes(title_text="<b>อุณหภูมิ (°C)</b>", secondary_y=False, color='#FF4B4B', showgrid=False)
        fig_dual.update_yaxes(title_text="<b>ความชื้นอากาศ (%)</b>", secondary_y=True, color='#00D4FF', showgrid=True, gridcolor='#31333F')
        
        st.plotly_chart(fig_dual, use_container_width=True)

    # --- ส่วนของระบบพยากรณ์ความเสี่ยงโรคพืชและความเครียด ---
    st.divider()
    st.subheader("🛡️ ระบบประเมินความเสี่ยงและสุขภาพพืช (Plant Health & Risk)")

    # Logic 1: เชื้อรา
    if cur_temp > 30 and cur_humid > 80:
        mold_stat, mold_desc, mold_color = "🔴 เสี่ยงสูงมาก (High Risk)", "อากาศร้อนชื้นจัด เสี่ยงเกิดโรคโคนเน่า แนะนำให้พัดลมทำงาน MAX ด่วน", "error"
    elif cur_temp > 28 and cur_humid > 75:
        mold_stat, mold_desc, mold_color = "🟡 เฝ้าระวัง (Warning)", "อากาศเริ่มอบอ้าว ควรรักษาการถ่ายเทอากาศให้ดี", "warning"
    else:
        mold_stat, mold_desc, mold_color = "🟢 ปลอดภัย (Safe)", "สภาพอากาศถ่ายเทดี ระดับความต้านทานโรคอยู่ในเกณฑ์ปกติ", "success"

    # ✅ Logic 2: ความเครียด (อัปเดตใช้ PPFD เป็นเกณฑ์)
    # หาก PPFD > 150 คือแสงเข้มข้นมาก ถ้าอุณหภูมิพุ่งด้วยพืชจะเครียด
    if cur_temp > 33 and cur_ppfd > 150:
        stress_stat, stress_desc, stress_color = "🔴 พืชเครียดจัด (Severe Stress)", "แดดแรงและร้อนจัด ระวังใบไหม้ ควรพรางแสง", "error"
    elif cur_temp > 31 and cur_soil < 50:
        stress_stat, stress_desc, stress_color = "🟡 เสี่ยงขาดน้ำ (Water Stress)", "ร้อนแต่ดินเริ่มแห้ง พืชสูญเสียน้ำเร็วกว่าดูดซึม", "warning"
    else:
        stress_stat, stress_desc, stress_color = "🟢 สภาพปกติ (Optimal)", "พืชสังเคราะห์แสงและคายน้ำได้ดี", "success"

    # Logic 3: ดิน
    if cur_soil < 40:
        soil_stat, soil_desc, soil_color = "🔴 ดินแห้งเกินไป", "ควรรดน้ำทันทีเพื่อป้องกันรากแห้งตาย", "error"
    elif cur_soil > 85:
        soil_stat, soil_desc, soil_color = "🟡 ดินแฉะเกินไป", "ดินอุ้มน้ำมากเกินไประวังรากขาดออกซิเจน", "warning"
    else:
        soil_stat, soil_desc, soil_color = "🟢 ดินชุ่มชื้นพอดี", "ความชื้นเหมาะสมต่อการดูดซึมธาตุอาหาร", "success"

    # UI แสดงผล
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
        # คะแนนภาพรวม
        env_score = 100
        if cur_temp > 30 or cur_temp < 24: env_score -= 15
        if cur_humid > 80 or cur_humid < 50: env_score -= 15
        if cur_soil < 50 or cur_soil > 85: env_score -= 20
        
        # ✅ เปลี่ยนจาก f"{env_score}/100" เป็น f"{env_score} %"
        st.metric("🏆 ภาพรวมสภาพแวดล้อม (Overall Status)", f"{env_score} %")
        
        # เพิ่มปุ่ม Export CSV 
        st.markdown("---")
        st.markdown("#### 📥 นำข้อมูลไปวิเคราะห์ต่อ (Data Export)")
        csv_data = df.to_csv(index=False).encode('utf-8-sig') 
        st.download_button(
            label="📄 ดาวน์โหลดข้อมูลย้อนหลังทั้งหมด (.csv)",
            data=csv_data,
            file_name=f"MorningGlory_Data_{now_th.strftime('%Y%m%d_%H%M')}.csv",
            mime='text/csv',
            use_container_width=True 
        )

else:
    st.warning("🌙 ไม่พบข้อมูลในระบบ กำลังรอสัญญาณจาก ESP32...")