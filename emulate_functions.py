import asyncio
import logging
from typing import Any

from homeassistant.components import conversation
from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.const import ATTR_ENTITY_ID, ATTR_AREA_ID, ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound
import homeassistant.util.dt as dt_util

from custom_components.extended_openai_conversation.helpers import NativeFunctionExecutor

_LOGGER = logging.getLogger(__name__)

async def get_exposed_entities(hass: HomeAssistant):
    states = [
        state
        for state in hass.states.async_all()
        if async_should_expose(hass, conversation.DOMAIN, state.entity_id)
    ]
    entity_registry = hass.data["entity_registry"]
    exposed_entities = []
    for state in states:
        entity_id = state.entity_id
        entity = entity_registry.async_get(entity_id)
        attributes = state.attributes  # Get the entity attributes

        aliases = []
        if entity and entity.aliases:
            aliases = entity.aliases

        exposed_entities.append(
            {
                "entity_id": entity_id,
                "name": state.name,
                "state": hass.states.get(entity_id).state,
                "attributes": attributes,  # Include the attributes
                "aliases": aliases,
            }
        )
    return exposed_entities

async def execute_service_single(hass: HomeAssistant, service_argument, exposed_entities):
    domain = service_argument["domain"]
    service = service_argument["service"]
    service_data = service_argument.get("service_data", service_argument.get("data", {}))
    entity_id = service_data.get(ATTR_ENTITY_ID, service_argument.get(ATTR_ENTITY_ID))
    area_id = service_data.get(ATTR_AREA_ID)
    device_id = service_data.get(ATTR_DEVICE_ID)

    if isinstance(entity_id, str):
        entity_id = [e.strip() for e in entity_id.split(",")]
    service_data[ATTR_ENTITY_ID] = entity_id

    if entity_id is None and area_id is None and device_id is None:
        raise CallServiceError(domain, service, service_data)
    if not hass.services.has_service(domain, service):
        raise ServiceNotFound(domain, service)
    NativeFunctionExecutor.validate_entity_ids(hass, entity_id or [], exposed_entities)

    # Update service_data with attributes from entity.attributes
    for entity in exposed_entities:
        if entity["entity_id"] in entity_id:
            for attr, value in entity["attributes"].items():
                # Check if the attribute is supported by the entity and not a reserved key
                if attr in entity["attributes"] and attr not in NativeFunctionExecutor.RESERVED_KEYS:
                    try:
                        service_data[attr] = value
                    except Exception as e:
                        _LOGGER.warning(f"Error setting attribute '{attr}' for entity '{entity['entity_id']}': {e}")

    # Remove any reserved keys from the service_data dictionary
    for reserved_key in NativeFunctionExecutor.RESERVED_KEYS:
        service_data.pop(reserved_key, None)

    try:
        await hass.services.async_call(
            domain=domain,
            service=service,
            service_data=service_data,
        )
        return {"success": True}
    except HomeAssistantError as e:
        _LOGGER.error(e)
        return {"error": str(e)}

async def main(hass: HomeAssistant):
    exposed_entities = await get_exposed_entities(hass)
    service_argument = {
        "domain": "light",
        "service": "turn_on",
        "service_data": {
            "entity_id": "light.kitchen_lights"
        }
    }
    result = await execute_service_single(hass, service_argument, exposed_entities)
    print(result)

if __name__ == "__main__":
    # Initialize the Home Assistant core
    hass = HomeAssistant()
    hass.config.config_dir = "/path/to/config"  # Set the config directory path

    # Setup recorder
    hass.data["entity_registry"] = hass.helpers.entity_registry.async_get(hass)

    # Run the main function
    asyncio.run(main(hass))
