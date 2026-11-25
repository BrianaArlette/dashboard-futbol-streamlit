import os
from datetime import datetime, timezone
import pandas as pd
import plotly.express as px
import streamlit as st
from datos import BASE, ENDPOINT, TEMPORADA, RESULTADOS, cargar_respaldo, consultar_api, preparar_dataframe, filtrar, resumen

st.set_page_config(page_title='Brasileirão | Dashboard', page_icon='⚽', layout='wide')
AZUL = '#1C4C9A'
GRIS = '#B9C3D1'
COLORES = {'Victoria local': '#0072B2', 'Empate': '#E69F00', 'Victoria visitante': '#009E73'}


def token_configurado():
    token = os.getenv('FOOTBALL_DATA_TOKEN', '').strip()
    if token:
        return token
    try:
        token = str(st.secrets.get('football_data_token', '')).strip()
    except (FileNotFoundError, KeyError):
        token = ''
    if token:
        return token
    archivo = BASE / 'token.txt'
    return archivo.read_text(encoding='utf-8-sig').strip() if archivo.exists() else ''


@st.cache_data(ttl=300, show_spinner=False)
def obtener_datos(token):
    return consultar_api(token)


def mostrar(fig, x=None, y=None):
    fig.update_layout(height=340, margin=dict(l=12, r=12, t=18, b=15), showlegend=False,
                      xaxis_title=x, yaxis_title=y)
    st.plotly_chart(fig, use_container_width=True, config={'displaylogo': False})


st.title('Brasileirão Série A | 2026')
st.caption('Herramientas de Visualización · Resultados de fútbol · football-data.org')

with st.sidebar:
    st.header('Fuente de datos')
    token = token_configurado()
    if not token:
        token = st.text_input('API Key', type='password', help='Token de football-data.org. No se guarda en el repositorio.')
    actualizar = st.button('Consultar API en vivo', type='primary', use_container_width=True)
    respaldo = st.button('Usar datos de la práctica', use_container_width=True)

if 'datos' not in st.session_state or respaldo:
    st.session_state.datos = cargar_respaldo()
    st.session_state.fuente = 'Respaldo original · 7 de noviembre de 2026 (hora de México)'
    st.session_state.en_vivo = False
    st.session_state.error = ''

if actualizar:
    try:
        with st.spinner('Consultando football-data.org...'):
            nuevos = obtener_datos(token.strip())
            preparar_dataframe(nuevos)
        st.session_state.datos = nuevos
        st.session_state.fuente = 'API en vivo · HTTP 200 · ' + datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
        st.session_state.en_vivo = True
        st.session_state.error = ''
    except (ValueError, OSError) as exc:
        st.session_state.error = str(exc)

if st.session_state.error:
    st.warning(st.session_state.error + ' Se conservan los últimos datos disponibles.')
if st.session_state.en_vivo:
    st.success(st.session_state.fuente + ' (consulta en caché hasta 5 minutos)')
else:
    st.info(st.session_state.fuente)

bruto, limpio = preparar_dataframe(st.session_state.datos)
if limpio.empty:
    st.warning('No hay partidos finalizados con datos válidos.')
    st.stop()

with st.sidebar:
    st.divider()
    st.header('Filtros')
    equipos = sorted(set(limpio['equipo_local']) | set(limpio['equipo_visitante']))
    equipo = st.selectbox('Equipo (local o visitante)', ['Todos'] + equipos)
    minimo, maximo = int(limpio['jornada'].min()), int(limpio['jornada'].max())
    jornadas = st.slider('Jornadas', minimo, maximo, (minimo, maximo)) if minimo < maximo else (minimo, maximo)
    resultado = st.selectbox('Resultado', ['Todos'] + RESULTADOS)
    st.caption('Todos los gráficos y la tabla responden a estos filtros.')
    st.divider()
    st.markdown('[Documentación de la API](https://docs.football-data.org/general/v4/competition.html)')

seleccion = filtrar(limpio, equipo, jornadas, resultado)
a, b, c, d = st.columns(4)
a.metric('Partidos recibidos', f'{len(bruto):,}')
b.metric('Partidos analizados', f'{len(seleccion):,}')
c.metric('Goles totales', f'{int(seleccion.total_goles.sum()):,}')
d.metric('Goles por partido', f'{seleccion.total_goles.mean():.2f}' if len(seleccion) else '—')
st.caption(f'{len(limpio)} partidos válidos en la fuente; {len(bruto)-len(limpio)} excluidos por estado o datos incompletos. Los últimos tres indicadores aplican los filtros.')

if seleccion.empty:
    st.warning('No hay partidos que coincidan con los filtros seleccionados.')
    st.stop()

distribucion, resultados, relacion, evolucion = resumen(seleccion)
izq, der = st.columns(2)
with izq:
    st.subheader('1. Distribución de goles')
    moda = int(distribucion.loc[distribucion.partidos.idxmax(), 'goles'])
    fig = px.bar(distribucion, x='goles', y='partidos', text_auto=True)
    fig.update_traces(marker_color=[AZUL if g == moda else GRIS for g in distribucion.goles])
    fig.update_xaxes(dtick=1)
    mostrar(fig, 'Goles por partido', 'Partidos')
    st.caption(f'El total de goles más frecuente es {moda}.')
with der:
    st.subheader('2. Comparación de resultados')
    fig = px.bar(resultados, x='resultado', y='partidos', color='resultado', color_discrete_map=COLORES,
                 text_auto=True, hover_data={'porcentaje': ':.1f'})
    mostrar(fig, 'Resultado', 'Partidos')
    mayor = resultados.loc[resultados.partidos.idxmax()]
    st.caption(f'{mayor.resultado}: {mayor.partidos} partidos ({mayor.porcentaje:.1f} %).')
izq, der = st.columns(2)
with izq:
    st.subheader('3. Goles locales y visitantes')
    fig = px.scatter(relacion, x='goles_local', y='goles_visitante', size='partidos',
                     size_max=35, color_discrete_sequence=[AZUL])
    fig.update_xaxes(dtick=1)
    fig.update_yaxes(dtick=1)
    mostrar(fig, 'Goles del local', 'Goles del visitante')
    st.caption('El tamaño de cada punto indica cuántos partidos tuvieron ese marcador.')
with der:
    st.subheader('4. Evolución por jornada')
    fig = px.line(evolucion, x='jornada', y='promedio', markers=True,
                  hover_data=['partidos'], color_discrete_sequence=[AZUL])
    mostrar(fig, 'Jornada', 'Promedio de goles')
    st.caption('Se muestran las jornadas con partidos filtrados; las jornadas incompletas pueden variar.')

st.divider()
st.subheader('Detalle de partidos')
tabla = seleccion[['fecha','jornada','equipo_local','equipo_visitante','goles_local','goles_visitante','total_goles','resultado']].copy()
tabla['fecha'] = tabla['fecha'].dt.strftime('%d/%m/%Y')
st.dataframe(tabla, hide_index=True, use_container_width=True, height=340)
st.download_button('Descargar partidos filtrados (CSV)', tabla.to_csv(index=False).encode('utf-8-sig'),
                   'partidos_filtrados.csv', 'text/csv')
with st.expander('Consulta y calidad de los datos'):
    st.code(f'{ENDPOINT}?season={TEMPORADA}', language='text')
    st.write('Autenticación mediante encabezado X-Auth-Token. Se conservan partidos FINISHED con marcador, fecha y jornada válidos.')
    calidad = pd.DataFrame({'Columna': bruto.columns, 'Tipo original': bruto.dtypes.astype(str).values,
                            'Faltantes': bruto.isna().sum().values})
    st.dataframe(calidad, hide_index=True, use_container_width=True)
