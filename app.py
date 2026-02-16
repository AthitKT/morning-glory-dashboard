import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re

# --- 1. การเชื่อมต่อ (ระบบ Cache และสลับกุญแจ) ---
@st.cache_data(ttl=60)
def fetch_data_from_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # ดึงจาก Secrets สำหรับ Cloud
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("Project IOT")
        sheet = spreadsheet.get_worksheet(0)
        return pd.DataFrame(sheet.get_all_records())
    except Exception as e:
        # กรณีรันบนเครื่องตัวเอง (Local)
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name('project-iot-Dashboard.json', scope)
            client = gspread.authorize(creds)
            spreadsheet = client.open("Project IOT")
            sheet = spreadsheet.get_worksheet(0)
            return pd.DataFrame(sheet.get_all_records())
        except:
            st.error(f"❌ ระบบเชื่อมต่อมีปัญหา: {e}")
            return pd.DataFrame()

# --- 2. จัดการข้อมูล (Data Cleaning) ---
df_raw = fetch_data_from_sheets()

if not df_raw.empty:
    df = df_raw.copy()
    df.columns = df.columns.str.strip() # ตัดช่องว่างชื่อคอลัมน์
    df.rename(columns={'Air Humid':'AirHumid', 'Soil Humid':'SoilHumid', 'Light Lux':'LightLux', 'Air Temp':'AirTemp'}, inplace=True, errors='ignore')

    target_cols = ['AirTemp', 'AirHumid', 'LightLux', 'SoilHumid']
    for col in target_cols:
        if col in df.columns:
            # ลบ % และแปลงเป็นตัวเลข
            df[col] = df[col].astype(str).str.replace('%', '', regex=False)
            df[col] = pd.to_numeric(df[col], errors='coerce').ffill().fillna(0)

    df_graph = df.tail(2000)
    df_predict = df.tail(5000)
else:
    df = pd.DataFrame()

# --- 3. หน้าจอ Dashboard ---
st.set_page_config(page_title="Morning Glory AI - Pro", layout="wide")

# คืนค่า CSS ความสวยงาม
st.markdown("""
    <style>
    .main { background-color: #0E1117; color: #FFFFFF; }
    .stMetric { background-color: #1E2129; padding: 15px; border-radius: 10px; border: 1px solid #31333F; }
    div[data-testid="metric-container"] { color: #FFFFFF; }
    </style>
    """, unsafe_allow_html=True)

st.title("🌱 Morning Glory Smart Dashboard (Real-Time)")

if not df.empty:
    last_row = df.iloc[-1]
    st.subheader(f"📅 วันที่ปลูก: {last_row.get('Day', 'N/A')}")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🌡️ อุณหภูมิ", f"{last_row.get('AirTemp', 0):.2f} °C")
    col2.metric("💧 ความชื้นอากาศ", f"{last_row.get('AirHumid', 0):.2f}%")
    col3.metric("☀️ แสงสว่าง", f"{last_row.get('LightLux', 0):.2f} lx")
    col4.metric("🪴 ความชื้นดิน", f"{last_row.get('SoilHumid', 0):.2f}%")

    st.divider()
    option = st.radio("เลือกดูข้อมูล:", ('ทั้งหมด', 'อุณหภูมิ', 'ความชื้นอากาศ', 'แสงสว่าง', 'ความชื้นดิน'), horizontal=True)

    def create_plot(selected_option):
        fig = go.Figure()
        metrics = {
            'อุณหภูมิ': {'col': 'AirTemp', 'color': '#FF4B4B', 'label': 'อุณหภูมิ (°C)'},
            'ความชื้นอากาศ': {'col': 'AirHumid', 'color': '#00D4FF', 'label': 'ความชื้นอากาศ (%)'},
            'แสงสว่าง': {'col': 'LightLux', 'color': '#FFD700', 'label': 'แสงสว่าง (lx)'},
            'ความชื้นดิน': {'col': 'SoilHumid', 'color': '#00FF7F', 'label': 'ความชื้นดิน (%)'}
        }
        x_axis = df_graph['Timestamp']
        if selected_option == 'ทั้งหมด':
            for name, m in metrics.items():
                if m['col'] in df_graph.columns:
                    fig.add_trace(go.Scatter(x=x_axis, y=df_graph[m['col']], mode='lines', name=name, line=dict(color=m['color'])))
        else:
            m = metrics[selected_option]
            if m['col'] in df_graph.columns:
                actual_data = df_graph[m['col']].tolist()
                fig.add_trace(go.Scatter(x=x_axis, y=actual_data, mode='lines', name=selected_option, line=dict(color=m['color'], width=2)))
                # Predict 6 ชม. (36 จุด)
                try:
                    trend = df_predict[m['col']].ewm(span=50, adjust=False).mean().iloc[-1]
                    last_time = datetime.strptime(str(x_axis.iloc[-1]), "%d/%m/%Y, %H:%M:%S")
                    predict_times = [x_axis.iloc[-1]] + [(last_time + timedelta(minutes=10*i)).strftime("%d/%m/%Y, %H:%M:%S") for i in range(1, 37)]
                    fig.add_trace(go.Scatter(x=predict_times, y=[actual_data[-1]] + [trend]*36, mode='lines', name='คาดการณ์ (6 ชม.)', line=dict(color='white', dash='dot')))
                except: pass
        fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="white"), template="plotly_dark", hovermode="x unified")
        return fig

    st.plotly_chart(create_plot(option), use_container_width=True)

    # --- ส่วนสรุปการเติบโต (Microgreen specialized logic) ---
    st.divider()
    st.subheader("🔮 สรุปผลการวิเคราะห์ (Microgreen AI)")
    
    try:
        age = int(re.search(r'\d+', str(last_row['Day'])).group())
    except: age = 0

    if 'LightLux' in df_predict.columns:
        active_light = df_predict[df_predict['LightLux'] > 500]
        avg_light = active_light['LightLux'].mean() if not active_light.empty else 0
        avg_soil = df_predict['SoilHumid'].mean() if 'SoilHumid' in df_predict.columns else 0

        c1, c2 = st.columns(2)
        with c1:
            st.info(f"💡 **แสงช่วงกลางวัน:** {avg_light:.2f} lx")
            st.caption(f"💧 ความชื้นดินเฉลี่ย: {avg_soil:.0f}%")
        
        with c2:
            if age <= 2:
                st.warning(f"🌱 **ระยะ: บ่มเมล็ด (Day {age})**")
                st.write("รากกำลังเดิน ยังไม่มีความสูงเหนือดิน")
            else:
                base_rate = 2.0 if age <= 5 else 3.0
                stage_name = "ช่วงแทงยอด" if age <= 5 else "ช่วงยืดตัว"
                factor = 1.0
                note = "✅ แสงเพียงพอ"
                if avg_light < 800:
                    factor *= 1.1
                    note = "⚠️ แสงน้อย ต้นอาจยืด"
                if avg_soil < 40:
                    factor *= 0.3
                    note = "⛔ ดินแห้ง ต้นหยุดโต"
                
                final_rate = base_rate * factor
                st.success(f"🌿 **คาดการณ์:** สูงขึ้น ~{final_rate * 2:.1f} ซม. ใน 2 วัน")
                st.caption(f"ระยะ: {stage_name} | อัตราโต: {final_rate:.1f} ซม./วัน ({note})")

else:
    st.warning("🌙 ไม่พบข้อมูล... ตรวจสอบ Google Sheet และ Secrets")