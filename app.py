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

# --- 3. ตั้งค่าหน้าจอและ CSS ---
st.set_page_config(page_title="Morning Glory Dashboard", layout="wide")

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

# ==========================================
# 🎯 สร้าง Tabs เพื่อแยก 2 หน้าต่างหลัก
# ==========================================
tab_main, tab_compare = st.tabs(["🌱 สถานะเรียลไทม์ (Real-time)", "📊 เปรียบเทียบผลการทดลอง (Trial 1 vs Trial 2)"])

# ------------------------------------------
# ▶️ แท็บที่ 1: สถานะเรียลไทม์ (โค้ดเดิมของคุณทั้งหมด)
# ------------------------------------------
with tab_main:
    if not df.empty:
        last_row = df.iloc[-1]
        
        # ดึงค่าและคำนวณ PPFD ไว้ล่วงหน้า
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

        st.subheader(f"📅 วันที่ปลูก: วันที่ {last_row.get('Day', '?')}")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🌡️ อุณหภูมิ", f"{cur_temp:.2f} °C")
        col2.metric("💧 ความชื้นอากาศ", f"{cur_humid:.2f}%")
        col3.metric("☀️ แสง (PPFD)", f"{cur_ppfd:.2f} µmol/m²/s", help=f"เซนเซอร์จับได้: {cur_light:.0f} lx")
        col4.metric("🪴 ความชื้นดิน", f"{cur_soil:.2f}%")

        st.divider()

        # กราฟ Interactive
        st.subheader("📊 กราฟวิเคราะห์แนวโน้ม")
        
        option = st.radio(
            "เลือกดูข้อมูลที่ต้องการ:",
            ('ทั้งหมด', 'อุณหภูมิ', 'ความชื้นอากาศ', 'แสงสว่าง', 'ความชื้นดิน'),
            horizontal=True
        )

        def create_plot(selected_option):
            fig = go.Figure()
            
            metrics = {
                'อุณหภูมิ': {'col': 'AirTemp', 'color': '#FF4B4B', 'label': 'ค่าอุณหภูมิในอากาศ (°C)', 'min_ok': 24, 'max_ok': 31},
                'ความชื้นอากาศ': {'col': 'AirHumid', 'color': '#00D4FF', 'label': 'ค่าความชื้นในอากาศ (%)', 'min_ok': 50, 'max_ok': 80},
                'แสงสว่าง': {'col': 'LightLux', 'color': '#FFD700', 'label': 'ค่าความเข้มแสงสว่าง (lx)', 'min_ok': 1000, 'max_ok': 3000},
                'ความชื้นดิน': {'col': 'SoilHumid', 'color': '#00FF7F', 'label': 'ค่าความชื้นในดิน (%)', 'min_ok': 40, 'max_ok': 80}
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
                    
                    fig.add_hrect(
                        y0=m['min_ok'], y1=m['max_ok'], 
                        fillcolor="#00FF7F", opacity=0.1,
                        line_width=1.5, line_dash="dash", line_color="#00FF7F",
                        annotation_text="ช่วงที่เหมาะสม", annotation_position="top left",
                        annotation_font_color="#00FF7F", annotation_font_size=12
                    )
                    
                    fig.add_trace(go.Scatter(
                        x=x_axis, y=actual_data, mode='lines', 
                        name=f'ข้อมูล {selected_option}', line=dict(color=m['color'], width=2)
                    ))
                    
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

        st.plotly_chart(create_plot(option), use_container_width=True)
        
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

        st.divider()
        st.subheader("🛡️ ระบบประเมินความเสี่ยงและสุขภาพพืช (Plant Health & Risk)")

        recent_data = df.tail(20)
        avg_temp = recent_data['AirTemp'].mean()
        avg_humid = recent_data['AirHumid'].mean()

        if avg_temp > 30 and avg_humid > 80:
            mold_stat, mold_desc, mold_color = "🔴 เสี่ยงสูงมาก (High Risk)", "อากาศร้อนชื้นจัดอย่างต่อเนื่อง เสี่ยงเกิดโรคโคนเน่า", "error"
        elif avg_temp > 28 and avg_humid > 75:
            mold_stat, mold_desc, mold_color = "🟡 เฝ้าระวัง (Warning)", "อากาศเริ่มอบอ้าวสะสม ควรรักษาการถ่ายเทอากาศให้ดี", "warning"
        else:
            mold_stat, mold_desc, mold_color = "🟢 ปลอดภัย (Safe)", "สภาพอากาศโดยเฉลี่ยถ่ายเทดี อยู่ในเกณฑ์ปกติ", "success"

        if cur_temp > 33 and cur_ppfd > 150:
            stress_stat, stress_desc, stress_color = "🔴 พืชเครียดจัด (Severe Stress)", "แดดแรงและร้อนจัด ระวังใบไหม้ ควรพรางแสง", "error"
        elif cur_temp > 31 and cur_soil < 50:
            stress_stat, stress_desc, stress_color = "🟡 เสี่ยงขาดน้ำ (Water Stress)", "ร้อนแต่ดินเริ่มแห้ง พืชสูญเสียน้ำเร็วกว่าดูดซึม", "warning"
        else:
            stress_stat, stress_desc, stress_color = "🟢 สภาพปกติ (Optimal)", "พืชสังเคราะห์แสงและคายน้ำได้ดี", "success"

        if cur_soil < 40:
            soil_stat, soil_desc, soil_color = "🔴 ดินแห้งเกินไป", "ควรรดน้ำทันทีเพื่อป้องกันรากแห้งตาย", "error"
        elif cur_soil > 85:
            soil_stat, soil_desc, soil_color = "🟡 ดินแฉะเกินไป", "ดินอุ้มน้ำมากเกินไประวังรากขาดออกซิเจน", "warning"
        else:
            soil_stat, soil_desc, soil_color = "🟢 ดินชุ่มชื้นพอดี", "ความชื้นเหมาะสมต่อการดูดซึมธาตุอาหาร", "success"

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
            env_score = 100
            if cur_temp > 30 or cur_temp < 24: env_score -= 15
            if cur_humid > 80 or cur_humid < 50: env_score -= 15
            if cur_soil < 50 or cur_soil > 85: env_score -= 20
            
            st.metric("🏆 ภาพรวมสภาพแวดล้อม (Overall Status)", f"{env_score} %")
            
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


# ------------------------------------------
# ▶️ แท็บที่ 2: หน้าเปรียบเทียบผลการทดลอง
# ------------------------------------------
with tab_compare:
    st.header("📈 วิเคราะห์เปรียบเทียบผลการทดลอง (Interactive Data)")
    st.markdown("เปรียบเทียบข้อมูลการเจริญเติบโตที่วัดด้วยมือ และสภาพแวดล้อมโดยเฉลี่ยจากข้อมูลที่จัดเก็บในฐานข้อมูลเดียวกัน")
    
    # --- 0. ตรวจจับจำนวนรอบการทดลองจาก Database ก่อน ---
    total_detected_trials = 0
    if not df.empty and 'Day' in df.columns:
        df['Day_Numeric'] = pd.to_numeric(df['Day'], errors='coerce').fillna(0)
        condition_new_trial = df['Day_Numeric'].diff() < -1
        df['Trial_Number'] = condition_new_trial.cumsum() + 1
        total_detected_trials = df['Trial_Number'].max()

    # 📌 2.1 ส่วนเปรียบเทียบข้อมูลพืช (กรอกข้อมูลผ่านหน้าเว็บ)
    st.subheader("🌱 1. อัตราการเจริญเติบโต (กายภาพ)")
    st.caption("ปรับจำนวนรอบการทดลอง และกรอกตัวเลขในตารางด้านล่าง ระบบจะสร้างกราฟเปรียบเทียบให้อัตโนมัติ")
    
    # --- 1. เลือกจำนวนรอบการทดลอง ---
    col_set1, col_set2 = st.columns([1, 3])
    with col_set1:
        max_allowed_trials = max(1, total_detected_trials)
        num_trials = st.number_input(
            "📌 จำนวนรอบที่ต้องการเปรียบเทียบ:", 
            min_value=1, 
            max_value=max_allowed_trials, 
            value=min(2, max_allowed_trials), 
            help=f"ระบบตรวจพบข้อมูลจริง {total_detected_trials} รอบ"
        )
        
        if total_detected_trials > 0:
            st.success(f"ฐานข้อมูลพบ {total_detected_trials} รอบ")

    # --- 2. จัดการข้อมูลตารางด้วย Session State (ป้องกันข้อมูลหายเมื่อรีเฟรช) ---
    # จะทำก็ต่อเมื่อเปิดเว็บครั้งแรกเท่านั้น
    if 'growth_data' not in st.session_state:
        default_periods = ['วันที่ 4', 'วันที่ 6', 'วันที่ 8', 'วันที่ 10']
        init_data = {'Period': default_periods}
        
        default_stems_t1 = [2.0, 5.0, 8.0, 12.0]
        default_stems_t2 = [2.5, 6.0, 9.5, 15.5]
        default_leafs_t1 = [1.0, 2.5, 3.5, 4.5]
        default_leafs_t2 = [1.2, 3.0, 4.2, 5.8]
        
        for i in range(1, 6): # สร้างคอลัมน์เผื่อไว้เลย 5 รอบ
            if i == 1:
                init_data[f'Stem_Trial{i}'] = default_stems_t1
                init_data[f'Leaf_Trial{i}'] = default_leafs_t1
            elif i == 2:
                init_data[f'Stem_Trial{i}'] = default_stems_t2
                init_data[f'Leaf_Trial{i}'] = default_leafs_t2
            else:
                init_data[f'Stem_Trial{i}'] = [0.0] * len(default_periods)
                init_data[f'Leaf_Trial{i}'] = [0.0] * len(default_periods)
        
        st.session_state.growth_data = pd.DataFrame(init_data)

    # 🌟 ดึงข้อมูลมาแสดงตามจำนวนรอบ (num_trials) ที่เลือก
    display_cols = ['Period']
    for i in range(1, num_trials + 1):
        display_cols.extend([f'Stem_Trial{i}', f'Leaf_Trial{i}'])
        
    df_input = st.session_state.growth_data[display_cols]
    
    st.markdown("**(คลิกที่ตารางเพื่อแก้ไขตัวเลข, เลื่อนลงล่างสุดเพื่อกด + เพิ่มวันได้)**")
    
    # ตารางแบบกรอกได้
    edited_df = st.data_editor(
        df_input, 
        num_rows="dynamic", 
        use_container_width=True, 
        hide_index=True
    )
    
    # ✅ อัปเดตข้อมูลที่แก้กลับไปที่ Session State เพื่อบันทึกค่า
    updated_full_df = st.session_state.growth_data.copy()
    
    # กรณีที่มีการเพิ่มแถว (Add row)
    if len(edited_df) > len(updated_full_df):
        extra_rows = len(edited_df) - len(updated_full_df)
        new_rows = pd.DataFrame([[0.0] * len(updated_full_df.columns)] * extra_rows, columns=updated_full_df.columns)
        updated_full_df = pd.concat([updated_full_df, new_rows], ignore_index=True)
    # กรณีที่มีการลบแถว
    elif len(edited_df) < len(updated_full_df):
        updated_full_df = updated_full_df.iloc[:len(edited_df)].copy()
        
    # อัปเดตค่าจากการแก้ไข
    for col in display_cols:
        updated_full_df[col] = edited_df[col].values
        
    st.session_state.growth_data = updated_full_df

    # --- 3. สร้างกราฟจากข้อมูลในตาราง ---
    col_chart1, col_chart2 = st.columns(2)
    colors = ['#A0AEC0', '#00FF7F', '#FFD700', '#FF4B4B', '#00D4FF'] 
    
    with col_chart1:
        # กราฟแท่งเปรียบเทียบความยาวก้าน
        fig_stem = go.Figure()
        for i in range(1, num_trials + 1):
            col_name = f'Stem_Trial{i}'
            if col_name in edited_df.columns:
                plot_data = edited_df[edited_df[col_name] > 0]
                if not plot_data.empty:
                    fig_stem.add_trace(go.Bar(x=plot_data['Period'], y=plot_data[col_name], name=f'รอบที่ {i}', marker_color=colors[(i-1)%len(colors)]))
        fig_stem.update_layout(
            barmode='group', template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            title="📏 เปรียบเทียบความยาวก้าน (Stem Length)", yaxis_title="ความยาว (cm)", hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_stem, use_container_width=True)

    with col_chart2:
        # กราฟเส้นเปรียบเทียบขนาดใบ
        fig_leaf = go.Figure()
        for i in range(1, num_trials + 1):
            col_name = f'Leaf_Trial{i}'
            if col_name in edited_df.columns:
                plot_data = edited_df[edited_df[col_name] > 0]
                if not plot_data.empty:
                    fig_leaf.add_trace(go.Scatter(x=plot_data['Period'], y=plot_data[col_name], mode='lines+markers', name=f'รอบที่ {i}', line=dict(color=colors[(i-1)%len(colors)], width=3), marker=dict(size=8)))
        fig_leaf.update_layout(
            template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            title="🍃 เปรียบเทียบขนาดใบ (Leaf Width)", yaxis_title="ความกว้าง (cm)", hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_leaf, use_container_width=True)
        
    # --- 4. สรุป % การเติบโต (เทียบรอบล่าสุด กับรอบแรก) ---
    if num_trials >= 2 and len(edited_df) > 0:
        st.markdown(f"#### 🏆 สรุปผลประสิทธิภาพเชิงเปรียบเทียบ (เปรียบเทียบรอบที่ {num_trials} กับรอบที่ 1)")
        try:
            valid_stem_1 = edited_df[edited_df['Stem_Trial1'] > 0]['Stem_Trial1']
            valid_stem_last = edited_df[edited_df[f'Stem_Trial{num_trials}'] > 0][f'Stem_Trial{num_trials}']
            
            valid_leaf_1 = edited_df[edited_df['Leaf_Trial1'] > 0]['Leaf_Trial1']
            valid_leaf_last = edited_df[edited_df[f'Leaf_Trial{num_trials}'] > 0][f'Leaf_Trial{num_trials}']

            if not valid_stem_1.empty and not valid_stem_last.empty:
                stem_first_val = valid_stem_1.iloc[-1]
                stem_last_val = valid_stem_last.iloc[-1]
                stem_diff = ((stem_last_val - stem_first_val) / stem_first_val) * 100
                
                leaf_first_val = valid_leaf_1.iloc[-1] if not valid_leaf_1.empty else 1
                leaf_last_val = valid_leaf_last.iloc[-1] if not valid_leaf_last.empty else 1
                leaf_diff = ((leaf_last_val - leaf_first_val) / leaf_first_val) * 100
                
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric(f"ความยาวก้านสูงสุด รอบที่ {num_trials}", f"{stem_last_val} cm", f"{stem_diff:+.1f}% จากรอบที่ 1")
                col_m2.metric(f"ขนาดใบสูงสุด รอบที่ {num_trials}", f"{leaf_last_val} cm", f"{leaf_diff:+.1f}% จากรอบที่ 1")
            else:
                st.caption("โปรดกรอกข้อมูลความยาวในรอบล่าสุดให้มากกว่า 0 เพื่อคำนวณส่วนต่าง")
        except Exception as e:
            st.caption("กำลังรอข้อมูลเพื่อประมวลผล...")

    # 📌 2.2 ส่วนเปรียบเทียบเซนเซอร์อัตโนมัติ (แยกตามวันที่ปลูกจริง)
    st.divider()
    st.subheader("🌡️ 2. เปรียบเทียบค่าเฉลี่ยสภาพแวดล้อม (Sensor Averages)")
    
    if total_detected_trials > 0:
        fig_sensor = go.Figure()
        
        for i in range(1, num_trials + 1):
            df_chunk = df[df['Trial_Number'] == i]
            
            if not df_chunk.empty:
                avg_temp = df_chunk['AirTemp'].mean()
                avg_hum = df_chunk['AirHumid'].mean()
                avg_soil = df_chunk['SoilHumid'].mean()
                
                fig_sensor.add_trace(go.Bar(
                    x=['อุณหภูมิ (°C)', 'ความชื้นอากาศ (%)', 'ความชื้นดิน (%)'],
                    y=[avg_temp, avg_hum, avg_soil],
                    name=f'รอบที่ {i} (จำนวน {len(df_chunk)} ข้อมูล)', 
                    marker_color=colors[(i-1)%len(colors)]
                ))
                
        fig_sensor.update_layout(
            barmode='group', template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_sensor, use_container_width=True)
    else:
        st.info("กำลังรอข้อมูลเซนเซอร์สะสมให้เพียงพอ หรือไม่พบคอลัมน์ 'Day' ในฐานข้อมูล...")