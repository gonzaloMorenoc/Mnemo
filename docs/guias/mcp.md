# Conectar tu asistente de IA a Mnemo (MCP)

Mnemo expone la memoria del equipo de QA por **MCP** (Model Context Protocol), el
estándar con el que Claude Code, Cursor y GitHub Copilot hablan con herramientas
externas. Cuando un test falla, tu asistente puede preguntar a Mnemo qué sabe el equipo
de él: cómo se etiquetó (defecto real, intermitente, entorno…), **la razón que dio una
persona** y las lecciones o runbooks enlazados.

Es **de solo lectura**: el token no puede escribir, ingerir ni etiquetar nada. Mnemo no
llama a ningún LLM para responder: devuelve fuentes y tu asistente redacta.

## 1. Crea un token de lectura

En Mnemo: **Integraciones → Asistentes de IA · MCP (solo lectura)** (owner/admin).

- **Alcance:** un proyecto (recomendado para consultores externos: no verá otros) o toda
  la organización.
- **Caducidad:** 30 días, 90 días, 1 año o sin caducidad.

El token (`mnemo_rt_…`) **solo se muestra una vez**. Guárdalo como variable de entorno:

```bash
export MNEMO_READ_TOKEN="mnemo_rt_…"   # en tu ~/.zshrc o gestor de secretos
```

Nunca lo pegues en un fichero que vaya a un repositorio. Si se filtra, revócalo en la
misma pantalla: deja de funcionar al instante.

La URL del servidor es la del backend seguida de `/mcp`
(en producción: `https://gonzalo7-mnemo.hf.space/mcp`).

## 2. Configura tu cliente

### Claude Code

```bash
claude mcp add --transport http mnemo https://gonzalo7-mnemo.hf.space/mcp \
  --header "Authorization: Bearer $MNEMO_READ_TOKEN"
```

Compruébalo con `claude mcp list` o, dentro de una sesión, `/mcp`.

### Cursor

`~/.cursor/mcp.json` (global) o `.cursor/mcp.json` (del proyecto):

```json
{
  "mcpServers": {
    "mnemo": {
      "url": "https://gonzalo7-mnemo.hf.space/mcp",
      "headers": { "Authorization": "Bearer ${env:MNEMO_READ_TOKEN}" }
    }
  }
}
```

### VS Code (GitHub Copilot, modo agente)

`.vscode/mcp.json` — VS Code te pide el token la primera vez y lo guarda cifrado:

```json
{
  "servers": {
    "mnemo": {
      "type": "http",
      "url": "https://gonzalo7-mnemo.hf.space/mcp",
      "headers": { "Authorization": "Bearer ${input:mnemo-token}" }
    }
  },
  "inputs": [
    { "type": "promptString", "id": "mnemo-token",
      "description": "Token de lectura de Mnemo", "password": true }
  ]
}
```

## 3. Úsalo

Pregunta con naturalidad; el asistente elige la herramienta:

- «Falla `test_pago_tarjeta` con *TimeoutError: pasarela 504*. ¿Qué sabe el equipo?»
  → `get_failure_memory`
- «¿Qué sabemos del sandbox de pagos?» → `search_memory`
- «¿Cómo está la memoria del proyecto checkout?» → `get_project_overview`
- «¿Qué proyectos hay?» → `list_projects`

| Herramienta | Para qué |
|---|---|
| `list_projects` | Proyectos que alcanza tu token |
| `search_memory` | Buscar por significado en lecciones, runbooks, reglas y defectos |
| `get_failure_memory` | Lo que se sabe de un test que falla (por huella, nombre o parecido) |
| `get_project_overview` | Índice de continuidad, inventario y última acta de traspaso |

## Límites y seguridad

- **60 peticiones por minuto** por token (ráfagas de 20); por encima, 429 con `Retry-After`.
- Lo que devuelve Mnemo lo escribieron personas o vino de herramientas importadas: va
  marcado como **dato**, y el asistente no debe seguirlo como instrucciones.
- Se eliminan secretos y datos personales antes de responder, y cada campo se recorta.
- Cada llamada queda registrada (token, herramienta y resultado; nunca el texto).
- El backend gratuito se duerme si no se usa: la primera llamada puede tardar unos
  segundos en despertarlo.
