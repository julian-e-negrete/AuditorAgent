# Especificación Técnica: GLPI API Proxy v1.0

> **Fuente de Verdad**: Este documento es la referencia canónica del sistema. Los endpoints de GLPI listados en la Sección 8 fueron extraídos directamente del OpenAPI spec en `http://192.168.1.33/api.php/v2.2.0/doc.json`.

---

## 1. Visión General

| Campo | Valor |
|-------|-------|
| Nombre | GLPI API Proxy |
| Versión | 1.0.0 |
| Stack | Python 3.10+ / FastAPI / httpx |
| GLPI Target | `http://192.168.1.33:80` |
| Proxy Host | `0.0.0.0:8080` (accesible desde toda la red local) |

---

## 2. Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│  CLIENTE (PC en red local, Postman, etc.)                    │
│  http://192.168.1.38:8080/api/v2.2/...                       │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  GLPI API PROXY  (192.168.1.38:8080)                         │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ OAuth Mgr  │  │  Middleware  │  │  ProxyLogger (JSONL) │  │
│  └────────────┘  │  Logging     │  └──────────────────────┘  │
│                  └──────────────┘                            │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  FastAPI Router                                      │    │
│  │  POST /token  |  GET /Health  |  * /{resource}       │    │
│  └──────────────────────────────────────────────────────┘    │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP + Bearer Token
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  GLPI SERVER  (192.168.1.33:80)                              │
│  /api.php/v2.2/{resource}                                    │
└──────────────────────────────────────────────────────────────┘
```

### Componentes

| Componente | Archivo | Responsabilidad |
|---|---|---|
| OAuthManager | `app/services/oauth.py` | Obtiene y cachea tokens de GLPI |
| GLPIClient | `app/services/glpi_client.py` | Cliente HTTP hacia GLPI |
| ProxyLogger | `app/services/logger.py` | Logging JSONL de requests/responses |
| LoggingMiddleware | `app/middleware/logging.py` | Captura entrada/salida del proxy |
| Routes | `app/routes/` | token, health, proxy |

---

## 3. Acceso desde Red Local

El proxy escucha en `0.0.0.0` (configurable via `PROXY_HOST`), lo que lo hace accesible desde cualquier PC en la misma subred.

**IP del servidor proxy**: `192.168.1.38`  
**Puerto**: `8080`

Desde cualquier cliente en la red:
```
http://192.168.1.38:8080/api/v2.2/...
```

### Firewall (UFW)

UFW está actualmente **inactivo**. Si se activa en el futuro:

```bash
# Permitir tráfico al proxy desde la red local
sudo ufw allow from 192.168.1.0/24 to any port 8080

# Verificar
sudo ufw status
```

---

## 4. Flujo OAuth (Password Grant)

```
Cliente → POST /api/v2.2/token (client_id, client_secret, username, password)
       → Proxy valida credenciales contra variables de entorno
       → Proxy hace POST a GLPI /api.php/v2.2/token
       → GLPI devuelve { access_token, expires_in }
       → Proxy cachea token en memoria y lo retorna al cliente
       → Cliente usa Bearer token en requests subsiguientes
```

### Parámetros del token

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `grant_type` | string | sí | Debe ser `"password"` |
| `client_id` | string | sí | Debe coincidir con `GLPI_CLIENT_ID` |
| `client_secret` | string | sí | Debe coincidir con `GLPI_CLIENT_SECRET` |
| `username` | string | sí | Usuario GLPI |
| `password` | string | sí | Password del usuario |

### Gestión del token en caché

- Almacenado en memoria (no persiste entre reinicios)
- Se invalida automáticamente al expirar (`expires_in`)
- Si el cliente no envía `Authorization`, el proxy usa el token cacheado
- Si no hay token cacheado → `401 Unauthorized`

---

## 5. Headers Obligatorios hacia GLPI

Todas las peticiones upstream incluyen automáticamente:

| Header | Valor |
|---|---|
| `Accept` | `application/json` |
| `GLPI-Entity-Recursive` | `true` |
| `Accept-Language` | `en_GB` |
| `Authorization` | `Bearer <token>` |

---

## 6. Logging

**Archivo**: `./logs/requests.jsonl` (configurable via `LOG_DIR`)  
**Formato**: JSON Lines (una entrada por línea)  
**Rotación**: diaria, retención 30 días

### Estructura de cada entrada

```json
{
  "timestamp": "2026-03-14T12:00:00.000Z",
  "request_id": "uuid-v4",
  "type": "input | output | error",
  "direction": "client_to_proxy | proxy_to_glpi | glpi_to_proxy | proxy_to_client",
  "method": "GET",
  "path": "/api/v2.2/Administration/User",
  "headers": { "Authorization": "Bearer eyJ***" },
  "body": null,
  "status_code": 200,
  "response_time_ms": 142,
  "source_ip": "192.168.1.100",
  "error": null
}
```

Cada respuesta HTTP incluye el header `X-Request-ID` con el UUID de la entrada de log correspondiente.

Headers sensibles (`Authorization`, `password`, `client_secret`) son enmascarados automáticamente.

---

## 7. Endpoints del Proxy

Prefijo base: `/api/v2.2`

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/` | Info del servicio |
| `POST` | `/api/v2.2/token` | Obtener Bearer token (JSON o form-urlencoded) |
| `GET` | `/api/v2.2/Health` | Estado del proxy y conexión con GLPI |
| `GET` | `/api/v2.2/ping` | Liveness check |
| `GET/POST/PUT/PATCH/DELETE` | `/api/v2.2/{resource}` | Proxy genérico a cualquier endpoint GLPI |

El `{resource}` se reenvía a GLPI como `/api.php/v2.2/{resource}` preservando método, query params y body.

### Errores del proxy

| Código | Causa |
|---|---|
| `400` | `grant_type` no es `"password"` |
| `401` | Token ausente, inválido o credenciales incorrectas |
| `422` | Campos requeridos faltantes en `/token` |
| `502` | No se pudo conectar con el servidor GLPI |

---

## 8. Endpoints GLPI v2.2 (Fuente: OpenAPI doc.json)

> Extraídos de `http://192.168.1.33/api.php/v2.2.0/doc.json` el 2026-03-14.
> Para usar desde el proxy, anteponer `http://192.168.1.38:8080/api/v2.2` al path.
> Ejemplo: `GET /Administration/User` → `GET http://192.168.1.38:8080/api/v2.2/Administration/User`

### Convenciones

- `{id}` — ID numérico del recurso
- `GET /{Resource}` — listar colección (soporta query params de paginación/filtro)
- `POST /{Resource}` — crear nuevo recurso
- `PATCH /{Resource}/{id}` — actualizar parcialmente
- `DELETE /{Resource}/{id}` — eliminar
- `GET /{Resource}/{id}/Timeline` — historial de actividad (Tickets, Changes, Problems)
- `GET /{Resource}/{id}/Component/{type}` — componentes de hardware de un asset


### 8.1 Administration

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Administration/ApprovalSubstitute` | Listar sustitutos de aprobación |
| `POST` | `/Administration/ApprovalSubstitute` | Crear sustituto |
| `GET` | `/Administration/ApprovalSubstitute/{id}` | Obtener sustituto |
| `DELETE` | `/Administration/ApprovalSubstitute/{id}` | Eliminar sustituto |
| `GET` | `/Administration/Entity` | Listar entidades |
| `POST` | `/Administration/Entity` | Crear entidad |
| `GET` | `/Administration/Entity/{id}` | Obtener entidad |
| `PATCH` | `/Administration/Entity/{id}` | Actualizar entidad |
| `DELETE` | `/Administration/Entity/{id}` | Eliminar entidad |
| `GET` | `/Administration/EventLog` | Listar log de eventos |
| `GET` | `/Administration/EventLog/{id}` | Obtener evento |
| `GET` | `/Administration/Group` | Listar grupos |
| `POST` | `/Administration/Group` | Crear grupo |
| `GET` | `/Administration/Group/{id}` | Obtener grupo |
| `PATCH` | `/Administration/Group/{id}` | Actualizar grupo |
| `DELETE` | `/Administration/Group/{id}` | Eliminar grupo |
| `GET` | `/Administration/Profile` | Listar perfiles |
| `POST` | `/Administration/Profile` | Crear perfil |
| `GET` | `/Administration/Profile/{id}` | Obtener perfil |
| `PATCH` | `/Administration/Profile/{id}` | Actualizar perfil |
| `DELETE` | `/Administration/Profile/{id}` | Eliminar perfil |
| `GET` | `/Administration/User` | Listar usuarios |
| `POST` | `/Administration/User` | Crear usuario |
| `GET` | `/Administration/User/Me` | Usuario autenticado actual |
| `GET` | `/Administration/User/Me/Email` | Emails del usuario actual |
| `POST` | `/Administration/User/Me/Email` | Agregar email |
| `GET` | `/Administration/User/Me/Email/{id}` | Obtener email |
| `GET` | `/Administration/User/Me/Emails/Default` | Email por defecto |
| `GET` | `/Administration/User/Me/ManagedItem` | Items gestionados por el usuario actual |
| `GET` | `/Administration/User/Me/Picture` | Foto del usuario actual |
| `GET` | `/Administration/User/Me/Preference` | Preferencias del usuario actual |
| `PATCH` | `/Administration/User/Me/Preference` | Actualizar preferencias |
| `GET` | `/Administration/User/Me/UsedItem` | Items usados por el usuario actual |
| `GET` | `/Administration/User/{id}` | Obtener usuario por ID |
| `PATCH` | `/Administration/User/{id}` | Actualizar usuario |
| `DELETE` | `/Administration/User/{id}` | Eliminar usuario |
| `GET` | `/Administration/User/{id}/ManagedItem` | Items gestionados |
| `GET` | `/Administration/User/{id}/Picture` | Foto del usuario |
| `GET` | `/Administration/User/{id}/Preference` | Preferencias |
| `PATCH` | `/Administration/User/{id}/Preference` | Actualizar preferencias |
| `GET` | `/Administration/User/{id}/UsedItem` | Items usados |
| `GET` | `/Administration/User/username/{username}` | Obtener usuario por nombre |
| `PATCH` | `/Administration/User/username/{username}` | Actualizar por nombre |
| `DELETE` | `/Administration/User/username/{username}` | Eliminar por nombre |
| `GET` | `/Administration/UserCategory` | Listar categorías de usuario |
| `POST` | `/Administration/UserCategory` | Crear categoría |
| `GET` | `/Administration/UserCategory/{id}` | Obtener categoría |
| `PATCH` | `/Administration/UserCategory/{id}` | Actualizar categoría |
| `DELETE` | `/Administration/UserCategory/{id}` | Eliminar categoría |
| `GET` | `/Administration/UserTitle` | Listar títulos de usuario |
| `POST` | `/Administration/UserTitle` | Crear título |
| `GET` | `/Administration/UserTitle/{id}` | Obtener título |
| `PATCH` | `/Administration/UserTitle/{id}` | Actualizar título |
| `DELETE` | `/Administration/UserTitle/{id}` | Eliminar título |


### 8.2 Assistance (Tickets, Problems, Changes)

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Assistance/Ticket` | Listar tickets |
| `POST` | `/Assistance/Ticket` | Crear ticket |
| `GET` | `/Assistance/Ticket/{id}` | Obtener ticket |
| `PATCH` | `/Assistance/Ticket/{id}` | Actualizar ticket |
| `DELETE` | `/Assistance/Ticket/{id}` | Eliminar ticket |
| `GET` | `/Assistance/Ticket/{id}/TeamMember` | Miembros del equipo |
| `POST` | `/Assistance/Ticket/{id}/TeamMember` | Agregar miembro |
| `DELETE` | `/Assistance/Ticket/{id}/TeamMember` | Eliminar miembro |
| `GET` | `/Assistance/Ticket/{id}/TeamMember/{role}` | Miembros por rol |
| `GET` | `/Assistance/Ticket/{id}/Timeline` | Timeline completo |
| `GET/POST/PATCH/DELETE` | `/Assistance/Ticket/{id}/Timeline/Followup/{subitem_id}` | Seguimientos |
| `GET/POST/PATCH/DELETE` | `/Assistance/Ticket/{id}/Timeline/Task/{subitem_id}` | Tareas |
| `GET/POST/PATCH/DELETE` | `/Assistance/Ticket/{id}/Timeline/Solution/{subitem_id}` | Soluciones |
| `GET/POST/PATCH/DELETE` | `/Assistance/Ticket/{id}/Timeline/Validation/{subitem_id}` | Validaciones |
| `GET/POST/PATCH/DELETE` | `/Assistance/Ticket/{id}/Timeline/Document/{subitem_id}` | Documentos |
| `GET` | `/Assistance/Problem` | Listar problemas |
| `POST` | `/Assistance/Problem` | Crear problema |
| `GET` | `/Assistance/Problem/{id}` | Obtener problema |
| `PATCH` | `/Assistance/Problem/{id}` | Actualizar problema |
| `DELETE` | `/Assistance/Problem/{id}` | Eliminar problema |
| `GET/POST/PATCH/DELETE` | `/Assistance/Problem/{id}/Timeline/*` | Timeline del problema (igual que Ticket) |
| `GET` | `/Assistance/Change` | Listar cambios |
| `POST` | `/Assistance/Change` | Crear cambio |
| `GET` | `/Assistance/Change/{id}` | Obtener cambio |
| `PATCH` | `/Assistance/Change/{id}` | Actualizar cambio |
| `DELETE` | `/Assistance/Change/{id}` | Eliminar cambio |
| `GET/POST/PATCH/DELETE` | `/Assistance/Change/{id}/Timeline/*` | Timeline del cambio |
| `GET` | `/Assistance/RecurringTicket` | Listar tickets recurrentes |
| `POST` | `/Assistance/RecurringTicket` | Crear ticket recurrente |
| `GET` | `/Assistance/RecurringTicket/{id}` | Obtener ticket recurrente |
| `PATCH` | `/Assistance/RecurringTicket/{id}` | Actualizar |
| `DELETE` | `/Assistance/RecurringTicket/{id}` | Eliminar |
| `GET` | `/Assistance/RecurringChange` | Listar cambios recurrentes |
| `POST` | `/Assistance/RecurringChange` | Crear cambio recurrente |
| `GET` | `/Assistance/RecurringChange/{id}` | Obtener |
| `PATCH` | `/Assistance/RecurringChange/{id}` | Actualizar |
| `DELETE` | `/Assistance/RecurringChange/{id}` | Eliminar |
| `GET` | `/Assistance/ExternalEvent` | Listar eventos externos |
| `POST` | `/Assistance/ExternalEvent` | Crear evento externo |
| `GET` | `/Assistance/ExternalEvent/{id}` | Obtener |
| `PATCH` | `/Assistance/ExternalEvent/{id}` | Actualizar |
| `DELETE` | `/Assistance/ExternalEvent/{id}` | Eliminar |

### 8.3 Statistics

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Assistance/Stat` | Estadísticas generales |
| `GET` | `/Assistance/Stat/Ticket/Global` | Stats globales de tickets |
| `GET` | `/Assistance/Stat/Ticket/Asset` | Stats por asset |
| `GET` | `/Assistance/Stat/Ticket/Characteristics` | Stats por características |
| `GET` | `/Assistance/Stat/Ticket/Asset/Export` | Exportar stats |
| `GET` | `/Assistance/Stat/Change/Global` | Stats globales de cambios |
| `GET` | `/Assistance/Stat/Problem/Global` | Stats globales de problemas |


### 8.4 Assets

Los assets siguen un patrón uniforme. Tipos disponibles: `Computer`, `Monitor`, `NetworkEquipment`, `Printer`, `Phone`, `Peripheral`, `Software`, `SoftwareLicense`, `Appliance`, `Certificate`, `Cable`, `Cartridge`, `Consumable`, `Enclosure`, `PDU`, `PassiveDCEquipment`, `Rack`, `Socket`, `Unmanaged`.

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Assets/` | Listar tipos de assets disponibles |
| `GET` | `/Assets/Global` | Vista global de todos los assets |
| `GET` | `/Assets/{Type}` | Listar assets del tipo |
| `POST` | `/Assets/{Type}` | Crear asset |
| `GET` | `/Assets/{Type}/{id}` | Obtener asset |
| `PATCH` | `/Assets/{Type}/{id}` | Actualizar asset |
| `DELETE` | `/Assets/{Type}/{id}` | Eliminar asset |
| `GET` | `/Assets/{Type}/{id}/Infocom` | Información financiera |
| `POST` | `/Assets/{Type}/{id}/Infocom` | Crear infocom |
| `PATCH` | `/Assets/{Type}/{id}/Infocom` | Actualizar infocom |
| `DELETE` | `/Assets/{Type}/{id}/Infocom` | Eliminar infocom |
| `GET` | `/Assets/{Type}/{id}/Component/{ComponentType}` | Componentes de hardware |
| `GET` | `/Assets/{Type}/{asset_id}/SoftwareInstallation` | Software instalado |
| `POST` | `/Assets/{Type}/{asset_id}/SoftwareInstallation` | Registrar instalación |
| `PATCH` | `/Assets/{Type}/{asset_id}/SoftwareInstallation/{id}` | Actualizar instalación |
| `DELETE` | `/Assets/{Type}/{asset_id}/SoftwareInstallation/{id}` | Eliminar instalación |
| `GET` | `/Assets/{asset_itemtype}/{asset_id}/OSInstallation` | OS instalado |
| `POST` | `/Assets/{asset_itemtype}/{asset_id}/OSInstallation` | Registrar OS |

**Tipos de componentes** (`{ComponentType}`): `Battery`, `Camera`, `Case`, `Controller`, `Drive`, `Firmware`, `GenericDevice`, `GraphicCard`, `HardDrive`, `Memory`, `NetworkCard`, `PCIDevice`, `PowerSupply`, `Processor`, `SIMCard`, `Sensor`, `SoundCard`, `Systemboard`

#### Assets especiales

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Assets/Software/{software_id}/Version` | Versiones de software |
| `POST` | `/Assets/Software/{software_id}/Version` | Crear versión |
| `GET` | `/Assets/Software/{software_id}/Version/{id}` | Obtener versión |
| `PATCH` | `/Assets/Software/{software_id}/Version/{id}` | Actualizar versión |
| `DELETE` | `/Assets/Software/{software_id}/Version/{id}` | Eliminar versión |
| `GET` | `/Assets/Rack/{rack_id}/Item` | Items en rack |
| `POST` | `/Assets/Rack/{rack_id}/Item` | Agregar item al rack |
| `GET` | `/Assets/Rack/{rack_id}/Item/{id}` | Obtener item |
| `PATCH` | `/Assets/Rack/{rack_id}/Item/{id}` | Actualizar item |
| `DELETE` | `/Assets/Rack/{rack_id}/Item/{id}` | Eliminar item |
| `GET` | `/Assets/Custom/` | Listar tipos de assets personalizados |
| `GET` | `/Assets/Custom/{itemtype}` | Listar assets custom |
| `POST` | `/Assets/Custom/{itemtype}` | Crear asset custom |
| `GET` | `/Assets/Custom/{itemtype}/{id}` | Obtener asset custom |
| `PATCH` | `/Assets/Custom/{itemtype}/{id}` | Actualizar |
| `DELETE` | `/Assets/Custom/{itemtype}/{id}` | Eliminar |

### 8.5 Components

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Components` | Listar tipos de componentes |
| `GET` | `/Components/{Type}` | Listar componentes del tipo |
| `POST` | `/Components/{Type}` | Crear componente |
| `GET` | `/Components/{Type}/{id}` | Obtener componente |
| `PATCH` | `/Components/{Type}/{id}` | Actualizar componente |
| `DELETE` | `/Components/{Type}/{id}` | Eliminar componente |
| `GET` | `/Components/{Type}/{id}/Items` | Assets que usan este componente |
| `GET` | `/Components/{Type}/Items/{id}` | Obtener instancia de componente en asset |

**Tipos**: `Battery`, `Camera`, `Case`, `Controller`, `Drive`, `Firmware`, `GenericDevice`, `GraphicCard`, `HardDrive`, `Memory`, `NetworkCard`, `PCIDevice`, `PowerSupply`, `Processor`, `SIMCard`, `Sensor`, `SoundCard`, `Systemboard`

### 8.6 Management

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Management/` | Listar módulos de gestión |
| `GET/POST` | `/Management/Budget` | Presupuestos |
| `GET/PATCH/DELETE` | `/Management/Budget/{id}` | Presupuesto por ID |
| `GET/POST` | `/Management/Cluster` | Clusters |
| `GET/PATCH/DELETE` | `/Management/Cluster/{id}` | Cluster por ID |
| `GET/POST` | `/Management/Contact` | Contactos |
| `GET/PATCH/DELETE` | `/Management/Contact/{id}` | Contacto por ID |
| `GET/POST` | `/Management/Contract` | Contratos |
| `GET/PATCH/DELETE` | `/Management/Contract/{id}` | Contrato por ID |
| `GET/POST` | `/Management/DataCenter` | Data centers |
| `GET/PATCH/DELETE` | `/Management/DataCenter/{id}` | Data center por ID |
| `GET/POST` | `/Management/Database` | Bases de datos |
| `GET/PATCH/DELETE` | `/Management/Database/{id}` | Base de datos por ID |
| `GET/POST` | `/Management/DatabaseInstance` | Instancias de BD |
| `GET/PATCH/DELETE` | `/Management/DatabaseInstance/{id}` | Instancia por ID |
| `GET/POST` | `/Management/Document` | Documentos |
| `GET/PATCH/DELETE` | `/Management/Document/{id}` | Documento por ID |
| `GET` | `/Management/Document/{id}/Download` | Descargar documento |
| `GET/POST` | `/Management/Domain` | Dominios |
| `GET/PATCH/DELETE` | `/Management/Domain/{id}` | Dominio por ID |
| `GET/POST` | `/Management/License` | Licencias |
| `GET/PATCH/DELETE` | `/Management/License/{id}` | Licencia por ID |
| `GET/POST` | `/Management/Line` | Líneas |
| `GET/PATCH/DELETE` | `/Management/Line/{id}` | Línea por ID |
| `GET/POST` | `/Management/Supplier` | Proveedores |
| `GET/PATCH/DELETE` | `/Management/Supplier/{id}` | Proveedor por ID |


### 8.7 Dropdowns

Todos los dropdowns siguen el mismo patrón CRUD. Tipos disponibles:

`ApprovalStep`, `AutoUpdateSystem`, `BusinessCriticity`, `CableStrand`, `CableType`, `Calendar`, `CloseTime`, `DatabaseInstanceCategory`, `DatabaseInstanceType`, `DeniedMailContent`, `DenyList`, `DocumentCategory`, `DocumentType`, `EventCategory`, `FollowupTemplate`, `ITILCategory`, `Location`, `Manufacturer`, `NetworkPortFiberchannelType`, `PCIVendor`, `RequestType`, `SolutionTemplate`, `SolutionType`, `State`, `TaskCategory`, `TaskTemplate`, `USBVendor`, `ValidationTemplate`, `VirtualMachineModel`, `VirtualMachineState`, `VirtualMachineType`, `WifiNetwork`

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Dropdowns/` | Listar tipos de dropdowns |
| `GET` | `/Dropdowns/{Type}` | Listar valores |
| `POST` | `/Dropdowns/{Type}` | Crear valor |
| `GET` | `/Dropdowns/{Type}/{id}` | Obtener valor |
| `PATCH` | `/Dropdowns/{Type}/{id}` | Actualizar valor |
| `DELETE` | `/Dropdowns/{Type}/{id}` | Eliminar valor |

### 8.8 Project

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Project/` | Listar proyectos |
| `POST` | `/Project/` | Crear proyecto |
| `GET` | `/Project/{id}` | Obtener proyecto |
| `PATCH` | `/Project/{id}` | Actualizar proyecto |
| `DELETE` | `/Project/{id}` | Eliminar proyecto |
| `GET` | `/Project/Task` | Listar todas las tareas |
| `POST` | `/Project/Task` | Crear tarea |
| `GET` | `/Project/Task/{id}` | Obtener tarea |
| `PATCH` | `/Project/Task/{id}` | Actualizar tarea |
| `DELETE` | `/Project/Task/{id}` | Eliminar tarea |
| `GET` | `/Project/{project_id}/Task` | Tareas de un proyecto |
| `POST` | `/Project/{project_id}/Task` | Crear tarea en proyecto |

### 8.9 Knowledgebase

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Knowledgebase/Article` | Listar artículos |
| `POST` | `/Knowledgebase/Article` | Crear artículo |
| `GET` | `/Knowledgebase/Article/{article_id}` | Obtener artículo |
| `PATCH` | `/Knowledgebase/Article/{article_id}` | Actualizar artículo |
| `DELETE` | `/Knowledgebase/Article/{article_id}` | Eliminar artículo |
| `GET` | `/Knowledgebase/Article/{article_id}/Comment` | Comentarios |
| `POST` | `/Knowledgebase/Article/{article_id}/Comment` | Agregar comentario |
| `GET` | `/Knowledgebase/Article/{article_id}/Revision` | Revisiones |
| `GET` | `/Knowledgebase/Category` | Listar categorías |
| `POST` | `/Knowledgebase/Category` | Crear categoría |
| `GET` | `/Knowledgebase/Category/{id}` | Obtener categoría |
| `PATCH` | `/Knowledgebase/Category/{id}` | Actualizar categoría |
| `DELETE` | `/Knowledgebase/Category/{id}` | Eliminar categoría |

### 8.10 Notes (sub-recurso transversal)

Disponible en: `Appliance`, `Budget`, `CartridgeItem`, `Certificate`, `Change`, `Cluster`, `Computer`, `ConsumableItem`, `Contact`, `DCRoom`, `Database`, `DatabaseInstance`, `Domain`, `DomainRecord`, `Enclosure`, `Entity`, `Group`, `Line`, `Monitor`, `NetworkEquipment`, `Peripheral`, `Phone`, `Printer`, `Problem`, `Project`, `ProjectTask`, `Rack`, `Software`, `SoftwareLicense`, `Supplier`

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/{ItemType}/{items_id}/Note` | Listar notas |
| `POST` | `/{ItemType}/{items_id}/Note` | Crear nota |
| `GET` | `/{ItemType}/{items_id}/Note/{id}` | Obtener nota |
| `PATCH` | `/{ItemType}/{items_id}/Note/{id}` | Actualizar nota |
| `DELETE` | `/{ItemType}/{items_id}/Note/{id}` | Eliminar nota |

### 8.11 Rules

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Rule/Collection` | Listar colecciones de reglas |
| `GET` | `/Rule/Collection/{collection}/Rule` | Listar reglas |
| `POST` | `/Rule/Collection/{collection}/Rule` | Crear regla |
| `GET` | `/Rule/Collection/{collection}/Rule/{id}` | Obtener regla |
| `PATCH` | `/Rule/Collection/{collection}/Rule/{id}` | Actualizar regla |
| `DELETE` | `/Rule/Collection/{collection}/Rule/{id}` | Eliminar regla |
| `GET` | `/Rule/Collection/{collection}/Rule/{id}/Criteria` | Criterios |
| `GET` | `/Rule/Collection/{collection}/Rule/{id}/Action` | Acciones |
| `POST/PATCH/DELETE` | `/Rule/Collection/{collection}/Rule/{rule_id}/Criteria/{id}` | CRUD criterios |
| `POST/PATCH/DELETE` | `/Rule/Collection/{collection}/Rule/{rule_id}/Action/{id}` | CRUD acciones |

### 8.12 Setup

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Setup/` | Módulos de configuración |
| `GET` | `/Setup/Config` | Configuración general |
| `GET` | `/Setup/Config/{context}` | Config por contexto |
| `GET` | `/Setup/Config/{context}/{name}` | Valor de config |
| `PATCH` | `/Setup/Config/{context}/{name}` | Actualizar config |
| `DELETE` | `/Setup/Config/{context}/{name}` | Eliminar config |
| `GET` | `/Setup/LDAPDirectory` | Directorios LDAP |
| `POST` | `/Setup/LDAPDirectory` | Crear directorio LDAP |
| `GET` | `/Setup/LDAPDirectory/{id}` | Obtener directorio |
| `PATCH` | `/Setup/LDAPDirectory/{id}` | Actualizar directorio |
| `DELETE` | `/Setup/LDAPDirectory/{id}` | Eliminar directorio |

### 8.13 Tools

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/Tools/` | Módulos de herramientas |
| `GET/POST` | `/Tools/Reminder` | Recordatorios |
| `GET/PATCH/DELETE` | `/Tools/Reminder/{id}` | Recordatorio por ID |
| `GET/POST` | `/Tools/RSSFeed` | Feeds RSS |
| `GET/PATCH/DELETE` | `/Tools/RSSFeed/{id}` | Feed por ID |

### 8.14 Session / Status / GraphQL

| Método | Path GLPI | Descripción |
|---|---|---|
| `GET` | `/session` | Info de sesión actual |
| `GET` | `/Session/EntityTree` | Árbol de entidades |
| `GET/POST` | `/authorize` | OAuth authorization code flow |
| `POST` | `/token` | Obtener token OAuth |
| `GET` | `/status` | Estado del sistema |
| `GET` | `/status/all` | Estado de todos los servicios |
| `GET` | `/status/{service}` | Estado de un servicio |
| `POST` | `/GraphQL/` | Ejecutar query GraphQL |
| `GET` | `/GraphQL/Schema` | Schema GraphQL |
| `POST` | `/Transfer` | Transferir items entre entidades |

---

## 9. Guía Postman

### Paso 1 — Obtener token

```
POST http://192.168.1.38:8080/api/v2.2/token
Content-Type: application/json

{
  "grant_type": "password",
  "client_id": "<GLPI_CLIENT_ID>",
  "client_secret": "<GLPI_CLIENT_SECRET>",
  "username": "<GLPI_USERNAME>",
  "password": "<GLPI_PASSWORD>"
}
```

Guardar `access_token` de la respuesta.

### Paso 2 — Configurar variable de entorno en Postman

En el environment de Postman, crear variable `token` con el valor del `access_token`.

### Paso 3 — Usar en requests

En cada request, en la pestaña **Authorization**:
- Type: `Bearer Token`
- Token: `{{token}}`

O manualmente en Headers:
```
Authorization: Bearer {{token}}
```

### Ejemplos de requests

**Listar usuarios**
```
GET http://192.168.1.38:8080/api/v2.2/Administration/User
Authorization: Bearer {{token}}
```

**Crear ticket**
```
POST http://192.168.1.38:8080/api/v2.2/Assistance/Ticket
Authorization: Bearer {{token}}
Content-Type: application/json

{
  "name": "Impresora no funciona",
  "content": "La impresora del piso 2 no imprime.",
  "type": 1,
  "urgency": 3,
  "impact": 3,
  "priority": 3
}
```

**Obtener ticket por ID**
```
GET http://192.168.1.38:8080/api/v2.2/Assistance/Ticket/42
Authorization: Bearer {{token}}
```

**Agregar followup a ticket**
```
POST http://192.168.1.38:8080/api/v2.2/Assistance/Ticket/42/Timeline/Followup
Authorization: Bearer {{token}}
Content-Type: application/json

{
  "content": "Se revisó el equipo, se requiere técnico."
}
```

**Listar computadoras**
```
GET http://192.168.1.38:8080/api/v2.2/Assets/Computer
Authorization: Bearer {{token}}
```

**Verificar salud del proxy**
```
GET http://192.168.1.38:8080/api/v2.2/Health
```

---

## 10. Variables de Entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `GLPI_API_URL` | URL base del servidor GLPI | `http://192.168.1.33:80` |
| `GLPI_CLIENT_ID` | ID de cliente OAuth | `ad656bf9...` |
| `GLPI_CLIENT_SECRET` | Secreto del cliente OAuth | `415ade76...` |
| `GLPI_USERNAME` | Usuario GLPI | `admin` |
| `GLPI_PASSWORD` | Password del usuario | `secret` |
| `PROXY_HOST` | Bind address | `0.0.0.0` |
| `PROXY_PORT` | Puerto del proxy | `8080` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |
| `LOG_DIR` | Directorio de logs | `./logs` |
| `HTTP_TIMEOUT` | Timeout HTTP en segundos | `30` |

---

## 11. Estructura del Proyecto

```
glpi-api/
├── app/
│   ├── main.py              # FastAPI app, middleware
│   ├── config.py            # Settings (pydantic-settings, .env)
│   ├── models/
│   │   ├── token.py         # TokenRequest, TokenResponse, TokenData
│   │   └── requests.py      # HealthResponse, LogEntry, ProxyRequest
│   ├── services/
│   │   ├── oauth.py         # OAuthManager
│   │   ├── glpi_client.py   # GLPIClient
│   │   └── logger.py        # ProxyLogger
│   ├── routes/
│   │   ├── token.py         # POST /token
│   │   ├── health.py        # GET /Health, GET /ping
│   │   └── proxy.py         # Catch-all proxy
│   └── middleware/
│       └── logging.py       # Request/response logging
├── logs/                    # JSONL log output
├── .env.example
├── requirements.txt
└── setup_test_env.sh
```

---

## 12. Changelog

| Commit | Descripción |
|---|---|
| `65e32ae` | `/token` acepta JSON y form-urlencoded |
| `b5193b8` | Fix: `X-Request-ID` header correcto tras rebuild de respuesta |
| `a08a3a5` | Fix: URL hardcodeada en `proxy.py` reemplazada por `settings.glpi_api_url` |
| `a8458ca` | Fix: middleware captura body completo de la respuesta |
| `e2940cf` | Agrega script `setup_test_env.sh` |
| `5bd2e7b` | Implementación inicial: proxy, OAuth, logging middleware |
