"""Consulta y limpieza de los partidos de la Serie A de Brasil."""
import json
from pathlib import Path
import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
ENDPOINT = 'https://api.football-data.org/v4/competitions/BSA/matches'
TEMPORADA = 2026
RESULTADOS = ['Victoria local', 'Empate', 'Victoria visitante']
COLUMNAS = ['fecha', 'jornada', 'equipo_local', 'equipo_visitante', 'goles_local', 'goles_visitante', 'estado']


def cargar_respaldo():
    return json.loads((BASE / 'respuesta.json').read_text(encoding='utf-8-sig'))


def consultar_api(token):
    if not token.strip():
        raise ValueError('Configura el token de football-data.org.')
    try:
        respuesta = requests.get(ENDPOINT, params={'season': TEMPORADA},
                                 headers={'X-Auth-Token': token.strip(), 'Accept': 'application/json'}, timeout=30)
    except requests.RequestException as exc:
        raise ValueError('No fue posible conectar con la API. Revisa tu conexión.') from exc
    if respuesta.status_code != 200:
        motivos = {400: 'Solicitud inválida.', 401: 'Token inválido.', 403: 'Acceso no autorizado para este token o plan.', 429: 'Límite de solicitudes alcanzado.'}
        raise ValueError(f'HTTP {respuesta.status_code}: {motivos.get(respuesta.status_code, "No se pudo consultar la API.")}')
    try:
        data = respuesta.json()
    except ValueError as exc:
        raise ValueError('La API no devolvió un JSON válido.') from exc
    if not isinstance(data, dict) or not isinstance(data.get('matches'), list) or not data['matches']:
        raise ValueError('La respuesta no contiene partidos.')
    return data


def preparar_dataframe(data):
    if not isinstance(data, dict) or not isinstance(data.get('matches'), list):
        raise ValueError('No se encontró la lista de partidos.')
    filas = []
    for p in data['matches']:
        if not isinstance(p, dict):
            continue
        marcador = (p.get('score') or {}).get('fullTime') or {}
        filas.append({'fecha': p.get('utcDate'), 'jornada': p.get('matchday'),
                      'equipo_local': (p.get('homeTeam') or {}).get('name'),
                      'equipo_visitante': (p.get('awayTeam') or {}).get('name'),
                      'goles_local': marcador.get('home'), 'goles_visitante': marcador.get('away'),
                      'estado': p.get('status')})
    bruto = pd.DataFrame(filas, columns=COLUMNAS)
    df = bruto.copy()
    df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce', utc=True)
    for col in ['jornada', 'goles_local', 'goles_visitante']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df[df['estado'].eq('FINISHED')].dropna(subset=COLUMNAS).copy()
    df = df[(df['jornada'] >= 1) & (df['goles_local'] >= 0) & (df['goles_visitante'] >= 0)].copy()
    for col in ['jornada', 'goles_local', 'goles_visitante']:
        df[col] = df[col].astype(int)
    df['total_goles'] = df['goles_local'] + df['goles_visitante']
    df['resultado'] = 'Empate'
    df.loc[df['goles_local'] > df['goles_visitante'], 'resultado'] = 'Victoria local'
    df.loc[df['goles_local'] < df['goles_visitante'], 'resultado'] = 'Victoria visitante'
    return bruto, df.sort_values(['fecha', 'jornada']).reset_index(drop=True)


def filtrar(df, equipo, jornadas, resultado):
    salida = df[df['jornada'].between(*jornadas)]
    if equipo != 'Todos':
        salida = salida[(salida['equipo_local'] == equipo) | (salida['equipo_visitante'] == equipo)]
    if resultado != 'Todos':
        salida = salida[salida['resultado'] == resultado]
    return salida.copy()


def resumen(df):
    distribucion = df['total_goles'].value_counts().sort_index().rename_axis('goles').reset_index(name='partidos')
    resultados = df['resultado'].value_counts().reindex(RESULTADOS, fill_value=0).rename_axis('resultado').reset_index(name='partidos')
    resultados['porcentaje'] = resultados['partidos'] / max(len(df), 1) * 100
    relacion = df.groupby(['goles_local', 'goles_visitante']).size().reset_index(name='partidos')
    evolucion = df.groupby('jornada', as_index=False).agg(promedio=('total_goles','mean'), partidos=('total_goles','size'))
    return distribucion, resultados, relacion, evolucion
