# Spec Backend — Asignación de Chips RFID a Equipos
# STEH · chip-assigner feature

Documento para el equipo backend. Define los cambios necesarios en la
base de datos y los endpoints nuevos para soportar la asignación de
chips RFID a equipos médicos desde el frontend STEH.

---

## Contexto

El servicio `chip-assigner` (Python, WebSocket local) lee chips TAG RFID
con el lector YR9011 USB y entrega el `chip_id` al frontend.
El frontend luego llama al backend para persistir la asignación en PostgreSQL.

Flujo completo:

```
Admin
  │ 1. abre DevicesPage → selecciona equipo
  │ 2. click "Asignar Chip"
  ▼
Frontend (React)
  │ 3. conecta a ws://localhost:8765 (chip-assigner Python)
  │ 4. envía {"action": "scan"}
  │ 5. recibe {"type": "chip_detected", "chip_id": "5959"}
  │ 6. muestra chip_id al admin para confirmación
  │ 7. PATCH /api/devices/:id/chip  ← nuevo endpoint
  ▼
Backend (Node.js)
  │ 8. guarda chipId en Device (PostgreSQL)
  ▼
Agente tracker-intra (mini-PC)
  │ 9. detecta tag "5959" con antena YR8900
  │ 10. GET /api/devices/by-chip/5959  ← nuevo endpoint
  │     → sabe que es el equipo "Respirador UCI-2"
```

---

## 1. Cambios en Prisma Schema

Archivo: `prisma/schema.prisma`

Agregar tres campos al modelo `Device`:

```prisma
model Device {
  // --- campos existentes (no tocar) ---
  id               String    @id @default(cuid())
  hospitalId       String
  name             String
  type             String
  status           String
  currentLocation  String?
  expectedLocation String?
  // ... resto de campos existentes ...

  // --- campos nuevos ---
  chipId           String?   @unique   // EPC del tag RFID asignado
  chipAssignedAt   DateTime?           // timestamp de la asignación
  chipAssignedBy   String?             // userId de quien asignó

  // --- índice nuevo ---
  @@index([chipId])                    // lookup rápido por chip
}
```

**Notas sobre el schema:**
- `chipId` es opcional (`?`) — un equipo puede no tener chip asignado todavía
- `@unique` garantiza que el mismo chip no se asigne a dos equipos
- `chipAssignedBy` guarda el `userId` del admin que realizó la asignación (para auditoría)

**Migration:**
```bash
npx prisma migrate dev --name add_chip_assignment_to_device
```

---

## 2. Endpoints nuevos

### 2.1 Asignar chip a equipo

```
PATCH /api/devices/:id/chip
```

**Auth:** Bearer token de usuario (mismo que el resto de /api/devices)

**Request body:**
```json
{
  "chip_id": "5959"
}
```

**Respuesta exitosa — 200:**
```json
{
  "statusCode": 200,
  "message": "Chip asignado correctamente",
  "data": {
    "id": "clx123abc",
    "name": "Respirador UCI-2",
    "type": "respirador",
    "status": "active",
    "currentLocation": "UCI Planta 2",
    "expectedLocation": "UCI Planta 2",
    "chipId": "5959",
    "chipAssignedAt": "2026-05-04T14:30:00.000Z",
    "chipAssignedBy": "usr_adminxxx",
    "hospitalId": "hosp_abc"
  }
}
```

**Errores:**

| Status | errorCode | Cuándo |
|--------|-----------|--------|
| 400 | `VALIDATION_ERROR` | `chip_id` ausente o vacío |
| 404 | `DEVICE_NOT_FOUND` | El device `:id` no existe |
| 409 | `CHIP_ALREADY_ASSIGNED` | El `chip_id` ya está asignado a otro equipo |
| 403 | `TENANT_ACCESS_DENIED` | El device pertenece a otro hospital |

**Ejemplo de implementación (service):**
```javascript
async assignChip(deviceId, chipId, actorUserId, userHospitalId) {
  // 1. Buscar el device
  const device = await prisma.device.findUnique({ where: { id: deviceId } });
  if (!device) throw new AppError(404, 'Equipo no encontrado', 'DEVICE_NOT_FOUND');

  // 2. Validar tenant
  assertTenantAccess({ hospitalId: userHospitalId }, device.hospitalId);

  // 3. Verificar que el chip no esté en uso
  const existing = await prisma.device.findUnique({ where: { chipId } });
  if (existing && existing.id !== deviceId) {
    throw new AppError(409,
      `El chip ${chipId} ya está asignado al equipo "${existing.name}"`,
      'CHIP_ALREADY_ASSIGNED'
    );
  }

  // 4. Asignar
  const updated = await prisma.device.update({
    where: { id: deviceId },
    data: {
      chipId,
      chipAssignedAt: new Date(),
      chipAssignedBy: actorUserId,
    },
  });

  // 5. Audit log
  await auditService.createAuditLog({
    action: 'device.chip_assigned',
    resourceType: 'device',
    resourceId: deviceId,
    actorUserId,
    hospitalId: device.hospitalId,
    metadata: { chipId },
  });

  // 6. Notificar frontend en tiempo real (si aplica)
  emitToHospital(device.hospitalId, 'device.chip_assigned', { deviceId, chipId });

  return updated;
}
```

---

### 2.2 Desasignar chip de equipo

```
DELETE /api/devices/:id/chip
```

**Auth:** Bearer token de usuario

**Sin body.**

**Respuesta exitosa — 200:**
```json
{
  "statusCode": 200,
  "message": "Chip desasignado correctamente",
  "data": {
    "id": "clx123abc",
    "chipId": null,
    "chipAssignedAt": null,
    "chipAssignedBy": null
  }
}
```

**Errores:**

| Status | errorCode | Cuándo |
|--------|-----------|--------|
| 404 | `DEVICE_NOT_FOUND` | Device no existe |
| 400 | `DEVICE_HAS_NO_CHIP` | El device no tiene chip asignado |
| 403 | `TENANT_ACCESS_DENIED` | Device de otro hospital |

---

### 2.3 Buscar equipo por chip ID

Usado por el agente tracker-intra para resolver qué equipo físico
corresponde al tag detectado por la antena YR8900.

```
GET /api/devices/by-chip/:chipId
```

**Auth:** Bearer token del agente (`agt_xxx.yyy`) — mismo mecanismo que `/api/agent/events`

**Ejemplo:**
```
GET /api/devices/by-chip/5959
Authorization: Bearer agt_abc123.secretxyz
```

**Respuesta exitosa — 200:**
```json
{
  "statusCode": 200,
  "message": "Equipo encontrado",
  "data": {
    "id": "clx123abc",
    "name": "Respirador UCI-2",
    "type": "respirador",
    "status": "active",
    "currentLocation": "UCI Planta 2",
    "expectedLocation": "UCI Planta 2",
    "chipId": "5959",
    "hospitalId": "hosp_abc"
  }
}
```

**Errores:**

| Status | errorCode | Cuándo |
|--------|-----------|--------|
| 404 | `DEVICE_NOT_FOUND` | Ningún equipo tiene ese chip asignado |
| 401 | `UNAUTHORIZED` | Token de agente inválido |

**Nota importante:** Este endpoint lo llamará el tracker-intra al detectar un tag.
Debe ser eficiente (usa el índice `@@index([chipId])` del schema).

---

## 3. Cambios en endpoints existentes

### GET /api/devices y GET /api/devices/:id

Incluir los campos nuevos en la respuesta para que el frontend pueda
mostrar si el equipo ya tiene chip asignado:

```json
{
  "id": "clx123abc",
  "name": "Respirador UCI-2",
  "type": "respirador",
  "status": "active",
  "currentLocation": "UCI Planta 2",
  "expectedLocation": "UCI Planta 2",
  "chipId": "5959",           // null si no tiene chip
  "chipAssignedAt": "2026-05-04T14:30:00.000Z",  // null si no tiene chip
  "hospitalId": "hosp_abc"
}
```

Si el select de Prisma filtra campos explícitamente, agregar `chipId`,
`chipAssignedAt` y `chipAssignedBy` al select.

---

## 4. Registro de auditoría

Acciones nuevas para `auditService.createAuditLog`:

| action | Cuándo |
|--------|--------|
| `device.chip_assigned` | Se asigna un chip a un equipo |
| `device.chip_unassigned` | Se desasigna un chip de un equipo |

---

## 5. Resumen de archivos a crear/modificar

| Archivo | Acción |
|---------|--------|
| `prisma/schema.prisma` | Agregar `chipId`, `chipAssignedAt`, `chipAssignedBy` a `Device` |
| `prisma/migrations/...` | Generar con `prisma migrate dev` |
| `src/modules/devices/device.service.js` | Agregar `assignChip()`, `unassignChip()`, `findByChipId()` |
| `src/modules/devices/device.controller.js` | Agregar handlers para los 3 endpoints nuevos |
| `src/modules/devices/device.routes.js` | Registrar rutas nuevas |

---

## 6. Validación del chip_id

El formato del `chip_id` que entrega el YR9011 es hex uppercase,
típicamente 4 caracteres (ej: `"5959"`, `"8600"`).

Validación recomendada en el backend:
```javascript
// chip_id debe ser string hex de 2 a 24 caracteres
const CHIP_ID_REGEX = /^[0-9A-Fa-f]{2,24}$/;
if (!CHIP_ID_REGEX.test(chipId)) {
  throw new AppError(400, 'Formato de chip_id inválido', 'VALIDATION_ERROR');
}
// Normalizar a uppercase antes de guardar
chipId = chipId.toUpperCase();
```

**Importante:** Guardar siempre en uppercase para consistencia con
los IDs que reporta el agente tracker-intra (YR8900).
