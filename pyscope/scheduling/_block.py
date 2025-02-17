from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import (
    Column,
    ColumnElement,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Interval,
    String,
    Table,
    Uuid,
    type_coerce,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .status import Status

logger = logging.getLogger(__name__)
logger.debug("_block.py")

observer_block_association_table = Table(
    "observer_block_association_table",
    Base.metadata,
    Column("block_uuid", ForeignKey("block.uuid")),
    Column("observer_uuid", ForeignKey("observer.uuid")),
)


class _Block(Base):
    """
    Represents a time range in a `~pyscope.scheduling.Schedule` attributed to
    an `~pyscope.scheduling.Observer`.

    A `~pyscope.scheduling._Block` can be used to represent allocated time
    with a `~pyscope.scheduling.ScheduleBlock` or unallocated time with an
    `~pyscope.scheduling.UnallocableBlock`. The `~pyscope.scheduling._Block`
    class is a base class that should not be instantiated directly. Instead,
    use the `~pyscope.scheduling.ScheduleBlock` or
    `~pyscope.scheduling.UnallocableBlock` subclasses.

    Parameters
    ----------
    name : `str`, default : ""
        A user-defined name for the `~pyscope.scheduling._Block`. This
        parameter does not change the behavior of the
        `~pyscope.scheduling._Block`, but it can be useful for identifying
        the `~pyscope.scheduling._Block` in a schedule.

    description : `str`, default : ""
        A user-defined description for the `~pyscope.scheduling._Block`.
        Similar to the `name` parameter, this parameter does not change the
        behavior of the `~pyscope.scheduling._Block`.

    observer : `~pyscope.scheduling.Observer`, required
        Associate this `~pyscope.scheduling._Block` with an
        `~pyscope.scheduling.Observer`. The `~pyscope.scheduling.Observer` is
        a bookkeeping object for an `~pyscope.observatory.Observatory` with
        multiple users/user groups.

    config : `~pyscope.telrun.InstrumentConfiguration`, required
        The `~pyscope.telrun.InstrumentConfiguration` to use for the
        `~pyscope.scheduling._Block`. This
        `~pyscope.telrun.InstrumentConfiguration` will be
        used to set the telescope's `~pyscope.telrun.InstrumentConfiguration`
        at the start of the `~pyscope.scheduling._Block` and will act as the
        default for all `~pyscope.scheduling.Field` objects in the
        `~pyscope.scheduling._Block` if one has not been provided. If a
        `~pyscope.scheduling.Field` has a different
        `~pyscope.telrun.InstrumentConfiguration`, it will override the block
        `~pyscope.telrun.InstrumentConfiguration` for the duration of the
        `~pyscope.scheduling.Field`.

    schedule : `~pyscope.scheduling.Schedule`, default : `None`
        The `~pyscope.scheduling.Schedule` that the
        `~pyscope.scheduling._Block` is associated with. This parameter is
        set automatically when the `~pyscope.scheduling._Block` is added to a
        `~pyscope.scheduling.Schedule` and is essentially a convenience
        parameter for quickly adding a `~pyscope.scheduling._Block` to a
        `~pyscope.scheduling.Schedule`.

    See Also
    --------
    pyscope.scheduling.ScheduleBlock : A subclass of
        `~pyscope.scheduling._Block` that is used to schedule
        `~pyscope.scheduling.Field` objects in a
        `~pyscope.scheduling.Schedule`.
    pyscope.scheduling.UnallocableBlock : A subclass of
        `~pyscope.scheduling._Block` that is used to represent unallocated
        time in a `~pyscope.scheduling.Schedule`.
    pyscope.telrun.InstrumentConfiguration : A class that represents the
        configuration of the telescope.
    pyscope.scheduling.Field : A class that represents a field to observe.
    """

    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), init=False
    )
    """
    The time that the block was requested to be scheduled. This parameter
    is set automatically when the block is added to a
    `~pyscope.scheduling.Schedule` and is commonly used to track the order in
    which block objects were added for some prioritization schemes.
    """

    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), init=False
    )
    """
    The time that the block was scheduled. This parameter is set automatically
    when the block is scheduled by the `~pyscope.scheduling.Scheduler`.
    """

    status: Mapped[Status] = mapped_column(
        Enum, nullable=False, init=False, default=Status.UNSCHEDULED
    )
    """
    The status of the block. This parameter is used to track the state of
    the block and is set automatically at various stages of the scheduling
    and execution process. The `status` parameter is an `~enum.Enum` with the
    following possible values:

    * `~pyscope.scheduling.Status.UNSCHEDULED` : The block has not been
      scheduled.

    * `~pyscope.scheduling.Status.EXPIRED` : The block has expired and cannot
      be scheduled.

    * `~pyscope.scheduling.Status.INVALID` : The block is invalid and cannot
      be scheduled.

    * `~pyscope.scheduling.Status.QUEUED` : The block is queued for
      scheduling.

    * `~pyscope.scheduling.Status.SCHEDULED` : The block has been assigned a
      start time and is therefore scheduled.

    * `~pyscope.scheduling.Status.FAILED` : The block failed to execute.

    * `~pyscope.scheduling.Status.CANCELLED` : The block was cancelled before
      execution began.

    * `~pyscope.scheduling.Status.IN_PROGRESS` : The block is currently
      executing.

    * `~pyscope.scheduling.Status.COMPLETED` : The block has completed
      execution.

    """

    name: Mapped[str | None] = mapped_column(String)
    """
    A user-defined name for the block. This parameter does not change
    the behavior of the block, but it can be useful for identifying the
    block in a schedule.
    """

    description: Mapped[str | None] = mapped_column(String)
    """
    A user-defined description for the block. Similar to the `name`
    parameter, this parameter does not change the behavior of the block.
    """

    observer: Mapped[List[Observer]] = relationship(
        secondary=observer_block_association_table
    )
    """
    The list of `~pyscope.scheduling.Observer` objects associated with the
    block. A block can be associated with just an
    `~pyscope.scheduling.Observer` or multiple `~pyscope.scheduling.Observer`
    objects. These `~pyscope.scheduling.Observer` objects are used to track
    the users or user groups that are responsible for the block.

    .. attention::
        All block objects must be associated with at least one
        `~pyscope.scheduling.Observer`.
    """

    config_uuid: Mapped[Uuid] = mapped_column(
        ForeignKey("instrument_configuration.uuid"), init=False
    )
    """
    The UUID for the `~pyscope.telrun.InstrumentConfiguration` used as the
    default configuration for the block. See the `config` parameter for more
    information.
    """

    config: Mapped[InstrumentConfiguration] = relationship(
        back_populates="blocks"
    )
    """
    The `~pyscope.telrun.InstrumentConfiguration` used as the default
    configuration for the block. A default
    `~pyscope.telrun.InstrumentConfiguration` must be provided when creating
    a new block.

    .. attention::
        A default `~pyscope.telrun.InstrumentConfiguration` must be provided
        when creating a new block.
    """

    start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), init=False
    )
    """
    The start time of the block. This parameter is typically set by the
    `~pyscope.scheduling.Scheduler` when the block is scheduled but can be
    manually set by the user for certain block types.
    """

    duration: Mapped[timedelta | None] = mapped_column(
        Interval, default=timedelta(), init=False
    )
    """
    The duration of the block. Typically computed by the
    `~pyscope.scheduling.Scheduler` using the
    `~pyscope.scheduling.TelrunModel`, it can also be manually set by the
    user for certain block types.
    """

    schedule_uuid: Mapped[Uuid | None] = mapped_column(
        ForeignKey("schedule.uuid"), init=False
    )
    """
    The UUID for the `~pyscope.scheduling.Schedule` that the block is
    associated with. See the `schedule` parameter for more information.
    """

    schedule: Mapped[Schedule | None] = relationship(
        back_populates="blocks", kw_only=True
    )
    """
    The `~pyscope.scheduling.Schedule` that the block has been added to.

    .. note::
        A block can be associated with only one `~pyscope.scheduling.Schedule`
        and if associated, does not necessarily imply that the block has been
        scheduled. When first added to a `~pyscope.scheduling.Schedule`, the
        block must be queued and then scheduled by the
        `~pyscope.scheduling.Scheduler`.
    """

    execution_block: Mapped[ExecutionBlock | None] = relationship(
        back_populates="block", init=False
    )
    """
    The `~pyscope.telrun.ExecutionBlock` associated with the block.
    The `~pyscope.telrun.ExecutionBlock` is generated by
    `~pyscope.telrun.TelrunOperator` and contains information, statuses, and
    logs related to the execution of the block for review by the requesting
    user and debugging purposes by the observatory staff.
    """

    def __post_init__(self) -> None:
        logger.debug("_Block = %s" % self.__repr__)

    @hybrid_property
    def mid_time(self) -> datetime:
        """
        The midpoint time of the block. Automatically computed as the start
        time plus half the duration of the block.
        """
        return self.start_time + self.duration / 2

    @mid_time.inplace.setter
    def _mid_time_setter(self, value: datetime) -> None:
        self.start_time = value - self.duration / 2
        self.end_time = value + self.duration / 2

    @mid_time.inplace.expression
    @classmethod
    def _mid_time_expression(cls) -> ColumnElement[DateTime]:
        return type_coerce(cls.start_time + cls.duration / 2, DateTime)

    @mid_time.inplace.update_expression
    @classmethod
    def _mid_time_update_expression(
        cls, value: DateTime
    ) -> List[Tuple[DateTime, DateTime]]:
        return [
            (cls.start_time, type_coerce(value - cls.duration / 2, DateTime)),
            (cls.end_time, type_coerce(value + cls.duration / 2, DateTime)),
        ]

    @hybrid_property
    def end_time(self) -> datetime:
        """
        The end time of the block. Automatically computed as the start time
        plus the duration of the block.
        """
        return self.start_time + self.duration

    @end_time.inplace.setter
    def _end_time_setter(self, value: datetime) -> None:
        self.start_time = value - self.duration

    @end_time.inplace.expression
    @classmethod
    def _end_time_expression(cls) -> ColumnElement[DateTime]:
        return type_coerce(cls.start_time + cls.duration, DateTime)

    @end_time.inplace.update_expression
    @classmethod
    def _end_time_update_expression(
        cls, value: DateTime
    ) -> List[Tuple[DateTime, DateTime]]:
        return [(cls.start_time, type_coerce(value - cls.duration, DateTime))]


'''
_Block.__annotations__["uuid"] = Mapped[Uuid]
_Block.uuid.__doc__ = \
    """
    The universally unique identifier (UUID) for the database entry
    corresponding to the object. This UUID is generated automatically with
    `uuid.uuid4` when the object is created and is used to uniquely
    identify the object in the database. The UUID is a primary key for
    the table and is required to be unique for each entry. The UUID is
    not intended to be used as a human-readable identifier and should
    not be relied upon for that purpose.
    """
'''
