import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re 
from streamlit_autorefresh import st_autorefresh
import pytz

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
    df_predict = df.tail(5000) if len(df) > 5000 else df

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
    df = pd.DataFrame() 

# --- 3. หน้าจอ Dashboard ---
st.set_page_config(page_title="Morning Glory AI - Pro", layout="wide")

# ✅ เพิ่ม CSS สำหรับกล่อง Status มุมขวาบน
st.markdown("""
    <style>
    .main { background-color: #0E1117; color: #FFFFFF; }
    .stMetric { background-color: #1E2129; padding: 15px; border-radius: 10px; border: 1px solid #31333F; }
    div[data-testid="metric-container"] { color: #FFFFFF; }
    
    /* CSS สำหรับ Status Box */
    .status-container { display: flex; justify-content: flex-end; gap: 15px; align-items: center; height: 100%; padding-top: 15px; }
    .status-box { background-color: #1E2129; padding: 12px 20px; border-radius: 10px; border: 1px solid #31333F; text-align: right; min-width: 140px;}
    .status-label { font-size: 0.85em; color: #A0AEC0; display: block; margin-bottom: 2px;}
    .status-time { font-size: 0.7em; color: #888888; display: block; margin-top: 4px;}
    </style>
    """, unsafe_allow_html=True)

if not df.empty:
    last_row = df.iloc[-1]
    
    # ✅ ดึงค่าสถานะปัจจุบัน (ป้องกัน Error หากพิมพ์ชื่อคอลัมน์ใน Sheet ผิด)
    current_fan = str(last_row.get('Fan', 'N/A')).strip().upper()
    current_pump = str(last_row.get('Pump', 'N/A')).strip().upper()
    
    # ✅ ค้นหาเวลาที่ปั๊มทำงานล่าสุด
    last_pump_time = "ยังไม่พบข้อมูล"
    if 'Pump' in df.columns and 'Timestamp' in df.columns:
        # กรองเอาเฉพาะแถวที่ Pump เป็น ON
        df_pump_on = df[df['Pump'].astype(str).str.strip().str.upper() == 'ON']
        if not df_pump_on.empty:
            # ดึง Timestamp ของแถวสุดท้ายที่เจอ
            last_pump_time = str(df_pump_on.iloc[-1]['Timestamp'])
            # ลบปีออกให้สั้นลง (เช่น 18/2/2026, 19:23:53 -> 18/2, 19:23:53) ย่อให้ดูสวยงาม
            last_pump_time = last_pump_time.replace("/2026", "").replace("/2025", "").replace("/2024", "")

    # ✅ จัด Layout ส่วนหัว (Title ซ้าย, Status ขวา)
    header_col1, header_col2 = st.columns([2.5, 2])
    
    with header_col1:
        st.title("🌱 Morning Glory Smart Dashboard")
        st.caption(f"🔄 อัปเดตข้อมูลล่าสุดเมื่อ: {now_th.strftime('%H:%M:%S')} น. (รีเฟรชทุก 30 วินาที)")
        
    with header_col2:
        # กำหนดสีตามสถานะ
        fan_color = "#00D4FF" if current_fan == "MAX" else "#FFD700" # ฟ้า MAX / เหลือง MIN
        pump_color = "#00FF7F" if current_pump == "ON" else "#FF4B4B" # เขียว ON / แดง OFF
        
        # วาดกล่อง HTML
        st.markdown(f"""
            <div class="status-container">
                <div class="status-box">
                    <span class="status-label">พัดลม (Fan)</span>
                    <strong style="color: {fan_color}; font-size: 1.4em;">{current_fan}</strong>
                </div>
                <div class="status-box">
                    <span class="status-label">ปั๊มน้ำ (Pump)</span>
                    <strong style="color: {pump_color}; font-size: 1.4em;">{current_pump}</strong>
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
            x_axis = df_graph.index # สำรองกรณีไม่มีคอลัมน์ Timestamp

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
                    x=x_axis, 
                    y=actual_data, 
                    mode='lines', 
                    name=f'ข้อมูล {selected_option}', 
                    line=dict(color=m['color'], width=2)
                ))
                
                # --- Predict Logic (6 Hours) ---
                if m['col'] in df_predict.columns:
                    try:
                        series_predict = df_predict[m['col']]
                        trend = series_predict.ewm(span=50, adjust=False).mean().iloc[-1]
                        
                        predict_values = [actual_data[-1]]
                        for i in range(36): 
                            predict_values.append(trend) 
                        
                        last_time = datetime.strptime(str(x_axis.iloc[-1]), "%d/%m/%Y, %H:%M:%S")
                        predict_times = [x_axis.iloc[-1]]
                        
                        for i in range(1, 37):
                            next_time = last_time + timedelta(minutes=10 * i)
                            predict_times.append(next_time.strftime("%d/%m/%Y, %H:%M:%S"))

                        fig.add_trace(go.Scatter(
                            x=predict_times, 
                            y=predict_values, 
                            mode='lines', 
                            name='คาดการณ์ (6 ชม.)',
                            line=dict(color='white', width=2, dash='dot')
                        ))
                    except:
                        pass

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color="white"),
            xaxis=dict(title="เวลา (Timestamp)", gridcolor='#31333F', showgrid=True, nticks=10),
            yaxis=dict(title=y_label, gridcolor='#31333F', showgrid=True),
            hovermode="x unified",
            template="plotly_dark",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        return fig

    st.plotly_chart(create_plot(option), use_container_width=True)

    # --- ส่วนสรุปการเติบโต ---
    st.divider()
    st.subheader("🔮 สรุปผลการวิเคราะห์ (Microgreen AI)")
    
    try:
        current_day_str = str(last_row.get('Day', '0')) 
        day_match = re.search(r'\d+', current_day_str)
        plant_age = int(day_match.group()) if day_match else 0
    except:
        plant_age = 0

    if 'LightLux' in df_predict.columns and 'SoilHumid' in df_predict.columns:
        active_light_data = df_predict[df_predict['LightLux'] > 500]
        avg_light_on = active_light_data['LightLux'].mean() if not active_light_data.empty else 0
        avg_soil_humid = df_predict['SoilHumid'].mean()

        c1, c2 = st.columns(2)
        with c1:
            st.info(f"💡 **ความเข้มแสง (Day Time):** {avg_light_on:.0f} lx")
            st.caption(f"💧 ความชื้นดินเฉลี่ย: {avg_soil_humid:.0f}%")

        with c2:
            if plant_age <= 2:
                st.warning(f"🌱 **ระยะ: บ่มเมล็ด/รากงอก (Day {plant_age})**")
                st.write("ช่วงนี้เน้นรักษาความชื้น รากกำลังเดิน ยังไม่มีความสูงเหนือดิน")
            else:
                if plant_age <= 5:
                    base_rate = 2.0  
                    stage_name = "ช่วงแทงยอด (Sprouting)"
                else:
                    base_rate = 3.0  
                    stage_name = "ช่วงยืดตัว (Elongation)"
                
                factor = 1.0
                
                if avg_light_on < 800:
                    factor *= 1.1 
                    note = "⚠️ แสงน้อย ต้นอาจยืดเพรียว"
                else:
                    note = "✅ แสงเพียงพอ ต้นสมบูรณ์"

                if avg_soil_humid < 40:
                    factor *= 0.3 
                    note = "⛔ ดินแห้งเกินไป! ต้นหยุดโต"

                final_rate = base_rate * factor
                
                st.success(f"🌿 **คาดการณ์:** สูงขึ้น ~{final_rate * 2:.1f} ซม. ใน 2 วัน")
                st.caption(f"ระยะ: {stage_name} | อัตราโต: {final_rate:.1f} ซม./วัน ({note})")

else:
    st.warning("🌙 ไม่พบข้อมูลในระบบ กำลังรอสัญญาณจาก ESP32...")